"""经验向量文本与弱词词面重排 UT。"""
from app.repo_analysis.services.mr_experience.models import ExperiencePattern
from app.repo_analysis.services.mr_experience.pattern_vector import PatternVectorService


class TestPatternEmbedAndRerank:
    def test_embed_text_includes_files_and_plan(self):
        pattern = ExperiencePattern(
            title="鉴权校验集中化",
            scenario="接入 JWT 时",
            patterns=["统一 Token 校验入口"],
            source_commits=["abc"],
            plan=["抽取校验器", "挂中间件"],
            anchors=["app/utils/auth/"],
            relevant_files=["app/utils/auth/jwt_validator.py"],
        )
        text = PatternVectorService.build_embed_text(pattern)
        assert "jwt_validator" in text
        assert "抽取校验器" in text
        assert "auth" in text

    def test_lexical_boost_prefers_jwt_item(self):
        items = [
            {
                "title": "流式输出全链路",
                "scenario": "前端渲染",
                "patterns": ["yield 到 UI"],
                "similarity": 0.81,
            },
            {
                "title": "鉴权校验集中化",
                "scenario": "接入 JWT",
                "patterns": ["统一校验"],
                "relevant_files": ["app/utils/auth/jwt_validator.py"],
                "similarity": 0.55,
            },
        ]
        ranked = PatternVectorService.rerank_by_query("jwt", items)
        assert ranked[0]["title"] == "鉴权校验集中化"
        assert float(ranked[0]["similarity"]) > float(items[1]["similarity"])
