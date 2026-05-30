import asyncio
import hashlib
import logging
import re
from typing import Dict, List, Optional, Tuple
import numpy as np
from app.config.settings import settings
from app.code_analysis.constants import line_chunk_space_name, symbol_summary_space_name
from app.code_analysis.models.analysis_status import RepoAnalysisType as AnalysisType
from app.code_analysis.services.codeast.model import FileInfo
from app.code_analysis.services.codechunk.code_chunk import LineTextChunk
from app.code_analysis.services.codesummary.code_summary import CodeSummary
from app.code_analysis.services.codesummary.model import ContentType
from app.infrastructure.llms import embedding_factory
from app.infrastructure.vector_store import VECTOR_STORE_CONN
from app.utils.common import normalize_path


_TRIVIAL_SYM_NAME = re.compile(r"^(get|set)[A-Z_][A-Za-z0-9_]*$")
_TRIVIAL_GO_ACCESSOR = re.compile(r"^(Get|Set|Is)[A-Z][A-Za-z0-9_]*$")
_TRIVIAL_JAVA_CPP_ACCESSOR = re.compile(r"^(get|set|is)[A-Z][A-Za-z0-9_]*$")
_TRIVIAL_GO_SINGLE_RETURN = re.compile(r"(?ms)^\s*return\s+.+\s*$")
_TRIVIAL_JAVA_CPP_SINGLE_RETURN = re.compile(r"(?ms)^\s*return\s+[^;]+;\s*$")
_TRIVIAL_JAVA_CPP_SINGLE_ASSIGN = re.compile(r"(?ms)^\s*(this\.)?[A-Za-z_][A-Za-z0-9_]*\s*=\s*[^;]+;\s*$")

# 向量化：大批次时拆成多段并发调用 model.encode，重叠网络/内部 batch 等待（受信号量限制防打爆 API）
_EMBED_PARALLEL_CHUNK_SIZE = 96
_EMBED_MAX_CONCURRENT = 3


class CodeVectorService:
    """代码分析结果向量化与落库：行块向量与符号（函数/类/方法）摘要向量。"""

    @staticmethod
    async def vectorize_and_store_line_chunks(repo_id: str, rel_file_path: str, chunks: List[LineTextChunk]) -> None:
        """将行切片文本批量嵌入向量，按仓与文件路径幂等写入向量库（先删后插）。"""
        rel_file_path = normalize_path(rel_file_path)
        if not chunks:
            return
        texts = [c.text for c in chunks]
        vectors = await CodeVectorService._embed_texts(texts)
        if not vectors:
            raise RuntimeError("line chunk向量化失败")
            
        dim = len(vectors[0])
        vector_field = f"q_{dim}_vec"
        space_name = line_chunk_space_name(repo_id, dim)
        await VECTOR_STORE_CONN.create_space(space_name, dim)
        await VECTOR_STORE_CONN.delete_records(
            space_name,
            {
                "repo_id": repo_id,
                "file_path": rel_file_path,
                "analysis_type": AnalysisType.LINE_CHUNK_VECTOR.value,
            },
        )
        records: List[Dict[str, object]] = []
        for idx, c in enumerate(chunks):
            stable_id = CodeVectorService._build_stable_id(
                repo_id=repo_id,
                file_path=rel_file_path,
                analysis_type=AnalysisType.LINE_CHUNK_VECTOR.value,
                start_line=c.start_line,
                end_line=c.end_line,
                extra=str(idx),
            )
            records.append(
                {
                    "id": stable_id,
                    "repo_id": repo_id,
                    "file_path": rel_file_path,
                    "analysis_type": AnalysisType.LINE_CHUNK_VECTOR.value,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "chunk_index": idx,
                    "content": c.text,
                    vector_field: vectors[idx],
                }
            )
        failed_ids = await VECTOR_STORE_CONN.insert_records(space_name, records)
        if failed_ids:
            raise RuntimeError(f"line chunk写入向量失败: {len(failed_ids)}")

    @staticmethod
    async def vectorize_and_store_symbol_summaries(
        repo_id: str,
        rel_file_path: str,
        file_info: Optional[FileInfo],
    ) -> None:
        """基于 AST 文件信息抽取函数/类/方法，经 LLM 摘要后嵌入并写入符号摘要向量空间。"""
        rel_file_path = normalize_path(rel_file_path)
        if not file_info:
            return
        
        symbols: List[Tuple[str, str, int, int, str, ContentType]] = []
        language = CodeVectorService._normalize_language(file_info.language)
        for fn in file_info.functions or []:
            name = fn.name or ""
            src = (fn.source_code or "").strip()
            if not src:
                continue

            if CodeVectorService._should_skip_symbol(name,src,language):
                continue

            symbols.append(
                (
                    "function",
                    name,
                    fn.start_line or 1,
                    fn.end_line or max(fn.start_line or 1, 1),
                    src,
                    ContentType.FUNCTION,
                )
            )
        
        for clz in file_info.classes or []:
            src = (clz.source_code or "").strip()
            if not src:
                continue
            symbols.append(
                (
                    "class",
                    clz.name,
                    clz.start_line or 1,
                    clz.end_line or max(clz.start_line or 1, 1),
                    src,
                    ContentType.CLASS,
                )
            )
            for method in clz.methods or []:
                mname = method.name or ""
                msrc = (method.source_code or "").strip()
                if not msrc:
                    continue

                if CodeVectorService._should_skip_symbol(mname,msrc,language):
                    continue

                symbols.append(
                    (
                        "method",
                        f"{clz.name}.{mname}",
                        method.start_line or 1,
                        method.end_line or max(method.start_line or 1, 1),
                        msrc,
                        ContentType.FUNCTION,
                    )
                )
        if not symbols:
            return
        
        # 生成符号摘要（并发可配置，默认与历史行为一致）
        sem = asyncio.Semaphore(max(1, settings.code_analysis_symbol_summary_llm_concurrency))
        async def one_summary(src: str, ct: ContentType) -> str:
            """对单个符号源码调用 LLM 摘要（受信号量限制并发）。"""
            async with sem:
                return await CodeSummary.llm_summarize(src, ct)

        summaries = await asyncio.gather(*[one_summary(src, ct) for _, _, _, _, src, ct in symbols])
        texts: List[str] = []
        for i, s in enumerate(summaries):
            t = (s or "").strip()
            if not t:
                t = CodeVectorService._fallback_summary_from_source(symbols[i][4], symbols[i][5])  
            texts.append(t)
        
        # 向量化符号摘要
        vectors = await CodeVectorService._embed_texts(texts)
        if not vectors:
            raise RuntimeError("symbol summary向量化失败")
        dim = len(vectors[0])
        vector_field = f"q_{dim}_vec"
        space_name = symbol_summary_space_name(repo_id, dim)
        await VECTOR_STORE_CONN.create_space(space_name, dim)
        await VECTOR_STORE_CONN.delete_records(
            space_name,
            {
                "repo_id": repo_id,
                "file_path": rel_file_path,
                "analysis_type": AnalysisType.SYMBOL_SUMMARY_VECTOR.value,
            },
        )
        records: List[Dict[str, object]] = []
        for idx, item in enumerate(symbols):
            symbol_kind, symbol_name, start_line, end_line, _, _ = item
            summary = texts[idx]
            stable_id = CodeVectorService._build_stable_id(
                repo_id=repo_id,
                file_path=rel_file_path,
                analysis_type=AnalysisType.SYMBOL_SUMMARY_VECTOR.value,
                start_line=start_line,
                end_line=end_line,
                extra=f"{symbol_kind}:{symbol_name}:{idx}",
            )
            records.append(
                {
                    "id": stable_id,
                    "repo_id": repo_id,
                    "file_path": rel_file_path,
                    "analysis_type": AnalysisType.SYMBOL_SUMMARY_VECTOR.value,
                    "symbol_kind": symbol_kind,
                    "symbol_name": symbol_name,
                    "start_line": start_line,
                    "end_line": end_line,
                    "summary": summary,
                    vector_field: vectors[idx],
                }
            )
        failed_ids = await VECTOR_STORE_CONN.insert_records(space_name, records)
        if failed_ids:
            raise RuntimeError(f"symbol summary写入向量失败: {len(failed_ids)}")

    @staticmethod
    def _normalize_language(language: Optional[str]) -> str:
        """归一化语言标识，避免大小写/空值影响过滤规则选择。"""
        return (language or "").strip().lower()

    @staticmethod
    def _non_comment_lines(src:str,language:str) -> List[str]:
        """提取去除空白和常见注释行后的代码行。"""
        lines = [ln for ln in src.splitlines() if ln.strip()]
        out: List[str] = []
        for ln in lines:
            s = ln.strip()
            if language == "python" and s.startswith("#"):
                continue
            if language in {"java","go","cpp","c"} and (s.startswith("//") or s.startswith("/*") or s.startswith("*") or s.startswith("*/")):
                continue
            out.append(ln)
        return out

    @staticmethod
    def _should_skip_symbol(name:str,src:str,language:str) -> bool:
        """按语言过滤低信息度符号函数（getter/setter/仅返回或仅赋值的小函数）。"""
        lines = CodeVectorService._non_comment_lines(src,language)
        if len(lines) > 8:
            return False
        body = "\n".join(lines)
        lowered = name.lower()

        if language == "python":
            if _TRIVIAL_SYM_NAME.match(name) or lowered.startswith("get_") or lowered.startswith("set_") or lowered.startswith("is_"):
                if len(lines) <= 4 and "return" in body and body.count("def ") <= 1:
                    return True
            return False

        if language == "go":
            if _TRIVIAL_GO_ACCESSOR.match(name) and len(lines) <= 5:
                non_sig = [it.strip() for it in lines if not it.strip().startswith("func ")]
                if len(non_sig) <= 2:
                    joined = " ".join(non_sig)
                    if _TRIVIAL_GO_SINGLE_RETURN.search(joined) or "=" in joined:
                        return True
            return False

        if language in {"java","cpp","c"}:
            if _TRIVIAL_JAVA_CPP_ACCESSOR.match(name) and len(lines) <= 7:
                non_sig = [it.strip() for it in lines if "(" not in it or ")" not in it]
                core = [it for it in non_sig if it not in {"{","}","};"}]
                if len(core) <= 2:
                    joined = " ".join(core)
                    if _TRIVIAL_JAVA_CPP_SINGLE_RETURN.search(joined) or _TRIVIAL_JAVA_CPP_SINGLE_ASSIGN.search(joined):
                        return True
            return False

        return False

    @staticmethod
    def _fallback_summary_from_source(source_code: str, ct: ContentType) -> str:
        """LLM 摘要为空时，用源码前几行拼成短文本作为回退描述。"""
        lines = [ln.strip() for ln in (source_code or "").splitlines() if ln.strip()]
        preview = " ".join(lines[:4])[:280]
        if ct == ContentType.CLASS:
            return f"类型摘要（回退）。内容预览: {preview}"
        return f"函数摘要（回退）。内容预览: {preview}"

    @staticmethod
    def _dedupe_texts(texts: List[str]) -> Tuple[List[str], List[int]]:
        """按全文去重，避免相同 chunk 文本重复调用 embedding。
        返回值
          unique: 去重后的文本列表
          index_map: 原文本列表中每个元素在 unique 中的索引，key 为文本，value 为其在 unique 中的索引
        """
        key_to_idx: Dict[str, int] = {}
        unique: List[str] = []
        index_map: List[int] = []
        for text in texts:
            if text not in key_to_idx:
                key_to_idx[text] = len(unique)  # 记录text在 unique 中的索引
                unique.append(text) 
            index_map.append(key_to_idx[text])  # 下标为原texts列表中的索引，值为text在unique中的索引，用于后续还原顺序
        return unique, index_map

    @staticmethod
    async def _encode_one_batch(model: object, batch: List[str]) -> List[List[float]]:
        """单次 model.encode，输出与 batch 等长的向量列表。"""
        encode = getattr(model, "encode")
        vectors, _ = await encode(batch)
        if vectors is None:
            return []
        arr = np.asarray(vectors)
        if arr.size == 0:
            return []
        if arr.ndim == 1:
            return [arr.tolist()]
        return [arr[i].tolist() for i in range(arr.shape[0])]

    @staticmethod
    async def _encode_unique_texts(model: object, unique: List[str]) -> List[List[float]]:
        """对去重后的文本列表编码；过长时按块并发 encode（每块仍走各后端的内部 batch/retry）。"""
        if not unique:
            return []
        if len(unique) <= _EMBED_PARALLEL_CHUNK_SIZE:
            out = await CodeVectorService._encode_one_batch(model, unique)
            if len(out) != len(unique):
                raise RuntimeError("embedding 返回数量与输入不一致")
            return out

        sem = asyncio.Semaphore(_EMBED_MAX_CONCURRENT)
        chunks = [
            unique[i : i + _EMBED_PARALLEL_CHUNK_SIZE]
            for i in range(0, len(unique), _EMBED_PARALLEL_CHUNK_SIZE)
        ]

        async def run_batch(batch: List[str]) -> List[List[float]]:
            async with sem:
                part = await CodeVectorService._encode_one_batch(model, batch)
                if len(part) != len(batch):
                    raise RuntimeError("embedding 返回数量与输入不一致")
                return part

        parts = await asyncio.gather(*[run_batch(c) for c in chunks])
        merged: List[List[float]] = []
        for p in parts:
            merged.extend(p)
        if len(merged) != len(unique):
            raise RuntimeError("embedding 合并结果与唯一文本数不一致")
        return merged

    @staticmethod
    async def _embed_texts(texts: List[str]) -> List[List[float]]:
        """调用全局 embedding：先去重，再分块并发 encode，最后按原顺序展开。"""
        if not texts:
            return []
        model = embedding_factory.create_model()
        if not model:
            raise RuntimeError("embedding模型创建失败")
        unique, index_map = CodeVectorService._dedupe_texts(texts)
        if len(unique) < len(texts):
            logging.info(
                "embedding 去重: %s 条 -> %s 条唯一文本，节省 %s 次向量计算",
                len(texts),
                len(unique),
                len(texts) - len(unique),
            )
        raw = await CodeVectorService._encode_unique_texts(model, unique)
        if not raw:
            return []
        return [raw[index] for index in index_map]

    @staticmethod
    def _build_stable_id(
        repo_id: str,
        file_path: str,
        analysis_type: str,
        start_line: int,
        end_line: int,
        extra: str = "",
    ) -> str:
        """用仓、路径、分析类型、行号与附加键生成 SHA1 稳定记录 ID，便于幂等更新。"""
        raw = f"{repo_id}|{file_path}|{analysis_type}|{start_line}|{end_line}|{extra}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    @staticmethod
    async def delete_repo_vector_records(repo_id: str) -> int:
        """按 repo_id 删除整仓向量记录（不依赖具体 file_path）。"""
        model = embedding_factory.create_model()
        if not model:
            return 0
        
        vectors, _ = await model.encode(["x"])
        if vectors is None or len(vectors) == 0:
            return 0
        dim = len(vectors[0])


        spaces = [
            line_chunk_space_name(repo_id, dim),
            symbol_summary_space_name(repo_id, dim),
        ]        
        deleted = 0
        for space_name in spaces:
            if not await VECTOR_STORE_CONN.space_exists(space_name):
                continue
            deleted += int(await VECTOR_STORE_CONN.delete_records(space_name, {"repo_id": repo_id}))
        return deleted

    @staticmethod
    async def delete_file_vector_records(repo_id: str, rel_file_path: str) -> int:
        """按 repo_id + file_path 删除指定文件的向量记录。"""
        rel_file_path = normalize_path(rel_file_path)
        model = embedding_factory.create_model()
        if not model:
            return 0

        vectors, _ = await model.encode(["x"])
        if vectors is None or len(vectors) == 0:
            return 0
        dim = len(vectors[0])

        spaces = [
            line_chunk_space_name(repo_id, dim),
            symbol_summary_space_name(repo_id, dim),
        ]
        deleted = 0
        for space_name in spaces:
            if not await VECTOR_STORE_CONN.space_exists(space_name):
                continue
            deleted += int(await VECTOR_STORE_CONN.delete_records(space_name, {"repo_id": repo_id, "file_path": rel_file_path}))
        return deleted