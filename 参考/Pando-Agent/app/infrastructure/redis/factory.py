import json
import asyncio
from enum import IntEnum
from typing import Optional, Any, List, Dict, Iterator
from redis.asyncio import ConnectionPool, Redis
import logging
import uuid
import time
from contextlib import asynccontextmanager, contextmanager
from app.config.settings import settings


class RedisSpaceEnum(IntEnum):
    """Redis空间枚举 - 精简版
    
    用于区分不同业务使用的Redis数据库，避免数据冲突
    现阶段不区分数据库，所有业务使用同一个Redis服务，不想指定类型情况下，可以使用默认值
    """
    DEFAULT = 0              # 默认空间 - 通用缓存、临时数据等
    SYSTEM = 1               # 系统级缓存 - 系统配置、元数据等
    
    USER = 10                # 用户相关 - 会话、缓存、验证码等
    
    AUTH = 20                # 认证相关 - 令牌、黑名单、OAuth等
    
    BUSINESS = 30            # 业务功能 - 缓存、队列、锁等
    
    LLM = 40                 # LLM相关 - 缓存、队列等
    
    MONITOR = 50             # 系统监控 - 限流、指标等

class RedisPool:
    """Redis连接池"""
    
    def __init__(self):
        self.config = settings
        self._pools: Dict[RedisSpaceEnum, ConnectionPool] = {}
        self._clients: Dict[RedisSpaceEnum, Redis] = {}
    
    def get_pool(self, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> ConnectionPool:
        """获取Redis连接池"""
        # 目前不论那种用途，都使用一个Redis服务，后续如果需要，可以扩展为
        if space not in self._pools:
            self._pools[space] = ConnectionPool(
                host=self.config.redis_host,
                port=self.config.redis_port,
                password=self.config.redis_password,
                db=space,
                max_connections=self.config.redis_max_connections,
                socket_timeout=self.config.redis_socket_timeout,
                socket_connect_timeout=self.config.redis_socket_connect_timeout,
                retry_on_timeout=self.config.redis_retry_on_timeout,
                decode_responses=self.config.redis_decode_responses
            )
        
        return self._pools[space]
    
    def get_client(self, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> Redis:
        """获取Redis客户端"""
        if space not in self._clients:
            pool = self.get_pool(space)
            self._clients[space] = Redis(connection_pool=pool)
        
        return self._clients[space]
    
    async def close_all(self):
        """关闭所有连接"""
        try:
            for pool in self._pools.values():
                await pool.disconnect()
            self._pools.clear()
            self._clients.clear()
            logging.info("Redis连接池已关闭")
        except Exception as e:
            logging.warning(f"关闭Redis连接池时出错: {e}")

class RedisMsg:
    """Redis消息类 - 用于消息队列"""
    
    def __init__(self, consumer, queue_name, group_name, msg_id, message):
        self.__consumer = consumer
        self.__queue_name = queue_name
        self.__group_name = group_name
        self.__msg_id = msg_id
        self.__message = json.loads(message["message"])

    async def ack(self):
        """确认消息"""
        try:
            await self.__consumer.xack(self.__queue_name, self.__group_name, self.__msg_id)
            return True
        except Exception as e:
            logging.warning(f"Redis消息确认失败 {self.__queue_name}: {e}")
        return False

    def get_message(self):
        """获取消息内容"""
        return self.__message

    def get_msg_id(self):
        """获取消息ID"""
        return self.__msg_id

class RedisClient:
    """Redis客户端封装类 - 提供完善的Redis操作接口"""
    _connet_pool = RedisPool()    # 连接池
    _lua_scripts = {}  # 类级别的Lua脚本缓存

    def _get_lua_script(self, space: RedisSpaceEnum, script_name: str):
        """获取缓存的Lua脚本"""
        cache_key = f"{space}_{script_name}"
        if cache_key not in self._lua_scripts:
            client = self._connet_pool.get_client(space)
            script_content = self._get_script_content(script_name)
            self._lua_scripts[cache_key] = client.register_script(script_content)
        return self._lua_scripts[cache_key]
    
    def _get_script_content(self, script_name: str) -> str:
        """获取Lua脚本内容"""
        scripts = {
            'delete_if_equal': """
                local current_value = redis.call('get', KEYS[1])
                if current_value and current_value == ARGV[1] then
                    redis.call('del', KEYS[1])
                    return 1
                end
                return 0
            """
        }
        return scripts.get(script_name, "")
    
    async def health_check(self, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """健康检查"""
        try:
            client = self._connet_pool.get_client(space)
            await client.ping()
            # 测试读写
            a, b = "xx", "yy"
            await client.setex(a, 3, b)
            result = await client.get(a)
            return result == b
        except Exception as e:
            logging.error(f"Redis健康检查失败: {e}")
        return False
    
    async def is_alive(self, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """检查Redis是否可用"""
        try:
            client = self._connet_pool.get_client(space)
            await client.ping()
            return True
        except Exception:
            return False
    
    async def close(self):
        """关闭连接"""
        await self._connet_pool.close_all()
    
    # =============================================================================
    # 基础操作
    # =============================================================================

    async def exist(self, k: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """检查键是否存在"""
        try:
            client = self._connet_pool.get_client(space)
            result = await client.exists(k)
            return bool(result)
        except Exception as e:
            logging.warning(f"Redis EXISTS操作失败 {k}: {e}")
            return False
    
    async def get(self, k: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> Any:
        """获取值"""
        try:
            client = self._connet_pool.get_client(space)
            return await client.get(k)
        except Exception as e:
            logging.warning(f"Redis GET操作失败 {k}: {e}")
            return None
        
    async def keys(self, pattern: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> List[str]:
        """获取匹配模式的键"""
        try:
            client = self._connet_pool.get_client(space)
            return await client.keys(pattern)
        except Exception as e:
            logging.warning(f"Redis KEYS操作失败 {pattern}: {e}")
            return []
    
    async def set(self, k: str, v: Any, exp: int = 3600, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """设置键值对"""
        try:
            client = self._connet_pool.get_client(space)
            result = await client.setex(k, exp, v)
            return bool(result)
        except Exception as e:
            logging.warning(f"Redis SET操作失败 {k}: {e}")
            return False
    
    async def set_obj(self, k: str, obj: Any, exp: int = 3600, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """设置对象（自动JSON序列化）"""
        try:
            client = self._connet_pool.get_client(space)
            json_str = json.dumps(obj, ensure_ascii=False)
            result = await client.setex(k, exp, json_str)
            return bool(result)
        except Exception as e:
            logging.warning(f"Redis SET_OBJ操作失败 {k}: {e}")
            return False
    
    async def delete(self, k: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """删除键"""
        try:
            client = self._connet_pool.get_client(space)
            result = await client.delete(k)
            return bool(result)
        except Exception as e:
            logging.warning(f"Redis DELETE操作失败 {k}: {e}")
            return False
    
    async def delete_if_equal(self, key: str, expected_value: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """条件删除 - 只有当值相等时才删除"""
        try:
            lua_script = self._get_lua_script(space, 'delete_if_equal')
            client = self._connet_pool.get_client(space)
            result = await lua_script(keys=[key], args=[expected_value], client=client)
            return bool(result)
        except Exception as e:
            logging.warning(f"Redis DELETE_IF_EQUAL操作失败 {key}: {e}")
            return False
    
    # =============================================================================
    # 哈希操作
    # =============================================================================

    async def hset(self, name: str, key: str, value: Any, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """设置哈希表字段"""
        try:
            client = self._connet_pool.get_client(space)
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            result = await client.hset(name, key, str(value))
            return bool(result)
        except Exception as e:
            logging.warning(f"Redis HSET操作失败 {name}.{key}: {e}")
            return False
    
    async def hget(self, name: str, key: str, default: Any = None, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> Any:
        """获取哈希表字段值"""
        try:
            client = self._connet_pool.get_client(space)
            value = await client.hget(name, key)
            if value is None:
                return default
            
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        except Exception as e:
            logging.warning(f"Redis HGET操作失败 {name}.{key}: {e}")
            return default
    
    async def hgetall(self, name: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> Dict[str, Any]:
        """获取哈希表所有字段"""
        try:
            client = self._connet_pool.get_client(space)
            data = await client.hgetall(name)
            result = {}
            for key, value in data.items():
                try:
                    result[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    result[key] = value
            return result
        except Exception as e:
            logging.warning(f"Redis HGETALL操作失败 {name}: {e}")
            return {}
    
    async def hdel(self, name: str, *keys: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> int:
        """删除哈希表字段"""
        try:
            client = self._connet_pool.get_client(space)
            return await client.hdel(name, *keys)
        except Exception as e:
            logging.warning(f"Redis HDEL操作失败 {name}: {e}")
            return 0
    
    # =============================================================================
    # 列表操作
    # =============================================================================
    
    async def lpush(self, name: str, *values: Any, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> int:
        """从左侧推入列表"""
        try:
            client = self._connet_pool.get_client(space)
            str_values = []
            for value in values:
                if isinstance(value, (dict, list)):
                    str_values.append(json.dumps(value, ensure_ascii=False))
                else:
                    str_values.append(str(value))
            return await client.lpush(name, *str_values)
        except Exception as e:
            logging.warning(f"Redis LPUSH操作失败 {name}: {e}")
            return 0
    
    async def rpop(self, name: str, default: Any = None, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> Any:
        """从右侧弹出列表元素"""
        try:
            client = self._connet_pool.get_client(space)
            value = await client.rpop(name)
            if value is None:
                return default
            
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return value
        except Exception as e:
            logging.warning(f"Redis RPOP操作失败 {name}: {e}")
            return default
    
    async def llen(self, name: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> int:
        """获取列表长度"""
        try:
            client = self._connet_pool.get_client(space)
            return await client.llen(name)
        except Exception as e:
            logging.warning(f"Redis LLEN操作失败 {name}: {e}")
            return 0
    
    # =============================================================================
    # 集合操作
    # =============================================================================
    
    async def sadd(self, key: str, member: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """向集合添加元素"""
        try:
            client = self._connet_pool.get_client(space)
            result = await client.sadd(key, member)
            return bool(result)
        except Exception as e:
            logging.warning(f"Redis SADD操作失败 {key}: {e}")
            return False
    
    async def srem(self, key: str, member: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """从集合删除元素"""
        try:
            client = self._connet_pool.get_client(space)
            result = await client.srem(key, member)
            return bool(result)
        except Exception as e:
            logging.warning(f"Redis SREM操作失败 {key}: {e}")
            return False
    
    async def smembers(self, key: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> set:
        """获取集合所有成员"""
        try:
            client = self._connet_pool.get_client(space)
            return await client.smembers(key)
        except Exception as e:
            logging.warning(f"Redis SMEMBERS操作失败 {key}: {e}")
            return set()
    
    async def sismember(self, key: str, member: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """检查元素是否在集合中"""
        try:
            client = self._connet_pool.get_client(space)
            result = await client.sismember(key, member)
            return bool(result)
        except Exception as e:
            logging.warning(f"Redis SISMEMBER操作失败 {key}: {e}")
            return False
    
    # =============================================================================
    # 有序集合操作
    # =============================================================================
    
    async def zadd(self, key: str, member: str, score: float, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """向有序集合添加元素"""
        try:
            client = self._connet_pool.get_client(space)
            result = await client.zadd(key, {member: score})
            return bool(result)
        except Exception as e:
            logging.warning(f"Redis ZADD操作失败 {key}: {e}")
            return False
    
    async def zcount(self, key: str, min: float, max: float, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> int:
        """统计有序集合中分数在指定范围内的元素数量"""
        try:
            client = self._connet_pool.get_client(space)
            return await client.zcount(key, min, max)
        except Exception as e:
            logging.warning(f"Redis ZCOUNT操作失败 {key}: {e}")
            return 0
    
    async def zpopmin(self, key: str, count: int, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> List:
        """弹出有序集合中分数最小的元素"""
        try:
            client = self._connet_pool.get_client(space)
            return await client.zpopmin(key, count)
        except Exception as e:
            logging.warning(f"Redis ZPOPMIN操作失败 {key}: {e}")
            return []
    
    async def zrangebyscore(self, key: str, min: float, max: float, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> List:
        """获取有序集合中分数在指定范围内的元素"""
        try:
            client = self._connet_pool.get_client(space)
            return await client.zrangebyscore(key, min, max)
        except Exception as e:
            logging.warning(f"Redis ZRANGEBYSCORE操作失败 {key}: {e}")
            return []
    
    # =============================================================================
    # 过期时间操作
    # =============================================================================
    
    async def expire(self, key: str, seconds: int, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """设置过期时间"""
        try:
            client = self._connet_pool.get_client(space)
            result = await client.expire(key, seconds)
            return bool(result)
        except Exception as e:
            logging.warning(f"Redis EXPIRE操作失败 {key}: {e}")
            return False
    
    async def ttl(self, key: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> int:
        """获取剩余过期时间"""
        try:
            client = self._connet_pool.get_client(space)
            return await client.ttl(key)
        except Exception as e:
            logging.warning(f"Redis TTL操作失败 {key}: {e}")
            return -2
    
    # =============================================================================
    # 事务操作
    # =============================================================================
    
    async def transaction(self, key: str, value: Any, expire: int = 3600, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """事务操作 - 原子性设置"""
        try:
            client = self._connet_pool.get_client(space)
            pipeline = client.pipeline(transaction=True)
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            pipeline.set(key, str(value), ex=expire, nx=True)
            results = await pipeline.execute()
            return bool(results[0])
        except Exception as e:
            logging.warning(f"Redis事务操作失败 {key}: {e}")
            return False
    
    # =============================================================================
    # 消息队列操作 (Redis Streams)
    # =============================================================================
    
    async def queue_product(self, queue: str, message: Any, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """生产消息到队列"""
        for _ in range(3):
            try:
                client = self._connet_pool.get_client(space)
                payload = {"message": json.dumps(message, ensure_ascii=False)}
                await client.xadd(queue, payload)
                return True
            except Exception as e:
                logging.exception(f"Redis队列生产失败 {queue}: {e}")
        return False
    
    async def queue_consumer(self, queue_name: str, group_name: str, consumer_name: str, msg_id: str = ">", space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> Optional[RedisMsg]:
        """消费队列消息"""
        for _ in range(3):
            try:
                client = self._connet_pool.get_client(space)
                # 检查并创建消费者组
                try:
                    group_info = await client.xinfo_groups(queue_name)
                    if not any(gi["name"] == group_name for gi in group_info):
                        await client.xgroup_create(queue_name, group_name, id="0", mkstream=True)
                except Exception:
                    # 如果队列不存在，创建队列和组
                    await client.xgroup_create(queue_name, group_name, id="0", mkstream=True)
                
                # 读取消息
                args = {
                    "groupname": group_name,
                    "consumername": consumer_name,
                    "count": 1,
                    "block": 5000,  # 5秒阻塞
                    "streams": {queue_name: msg_id},
                }
                messages = await client.xreadgroup(**args)
                
                if not messages:
                    return None
                
                stream, element_list = messages[0]
                if not element_list:
                    return None
                
                msg_id, payload = element_list[0]
                return RedisMsg(client, queue_name, group_name, msg_id, payload)
                
            except Exception as e:
                if str(e) == 'no such key':
                    pass
                else:
                    logging.exception(f"Redis队列消费失败 {queue_name}: {e}")
        return None
    
    async def get_unacked_iterator(self, queue_names: List[str], group_name: str, consumer_name: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> Iterator[RedisMsg]:
        """获取未确认消息迭代器"""
        try:
            client = self._connet_pool.get_client(space)
            for queue_name in queue_names:
                try:
                    group_info = await client.xinfo_groups(queue_name)
                except Exception as e:
                    if str(e) == 'no such key':
                        logging.warning(f"队列 {queue_name} 不存在")
                        continue
                
                if not any(gi["name"] == group_name for gi in group_info):
                    logging.warning(f"队列 {queue_name} 组 {group_name} 不存在")
                    continue
                
                current_min = 0
                while True:
                    payload = await self.queue_consumer(queue_name, group_name, consumer_name, current_min, space)
                    if not payload:
                        break
                    current_min = payload.get_msg_id()
                    logging.info(f"获取未确认消息 {queue_name} {consumer_name} {current_min}")
                    yield payload
        except Exception as e:
            logging.exception(f"获取未确认消息迭代器失败: {e}")
    
    async def get_pending_msg(self, queue: str, group_name: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> List[Dict]:
        """获取待处理消息"""
        try:
            client = self._connet_pool.get_client(space)
            messages = await client.xpending_range(queue, group_name, '-', '+', 10)
            return messages
        except Exception as e:
            if 'No such key' not in (str(e) or ''):
                logging.warning(f"获取待处理消息失败 {queue}: {e}")
        return []
    
    async def requeue_msg(self, queue: str, group_name: str, msg_id: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """重新入队消息"""
        for _ in range(3):
            try:
                client = self._connet_pool.get_client(space)
                messages = await client.xrange(queue, msg_id, msg_id)
                if messages:
                    await client.xadd(queue, messages[0][1])
                    await client.xack(queue, group_name, msg_id)
                    return True
            except Exception as e:
                logging.warning(f"重新入队消息失败 {queue}: {e}")
        return False
    
    async def queue_info(self, queue: str, group_name: str, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> Optional[Dict]:
        """获取队列信息"""
        for _ in range(3):
            try:
                client = self._connet_pool.get_client(space)
                groups = await client.xinfo_groups(queue)
                for group in groups:
                    if group["name"] == group_name:
                        return group
            except Exception as e:
                logging.warning(f"获取队列信息失败 {queue}: {e}")
        return None
    
    # =============================================================================
    # 分布式锁
    # =============================================================================
    
    def get_lock(self, lock_key: str, lock_value: str = None, timeout: int = 10, blocking_timeout: int = 1, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> "RedisDistributedLock":
        """获取分布式锁"""
        return RedisDistributedLock(space, lock_key, lock_value, timeout, blocking_timeout)
    
    @contextmanager
    def lock(self, lock_key: str, timeout: int = 10, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT):
        """分布式锁上下文管理器"""
        lock = self.get_lock(lock_key, timeout=timeout, space=space)
        try:
            if lock.acquire():
                yield lock
            else:
                raise RuntimeError(f"无法获取锁: {lock_key}")
        finally:
            lock.release()
    
    # =============================================================================
    # 批量操作
    # =============================================================================
    
    def pipeline(self, space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT):
        """获取管道对象"""
        client = self._connet_pool.get_client(space)
        return client.pipeline()
    
    async def mget(self, keys: List[str], space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> List[Any]:
        """批量获取"""
        try:
            client = self._connet_pool.get_client(space)
            values = await client.mget(keys)
            result = []
            for value in values:
                if value is None:
                    result.append(None)
                else:
                    try:
                        result.append(json.loads(value))
                    except (json.JSONDecodeError, TypeError):
                        result.append(value)
            return result
        except Exception as e:
            logging.warning(f"Redis MGET操作失败: {e}")
            return [None] * len(keys)
    
    async def mset(self, mapping: Dict[str, Any], space: RedisSpaceEnum = RedisSpaceEnum.DEFAULT) -> bool:
        """批量设置"""
        try:
            client = self._connet_pool.get_client(space)
            str_mapping = {}
            for key, value in mapping.items():
                if isinstance(value, (dict, list)):
                    str_mapping[key] = json.dumps(value, ensure_ascii=False)
                else:
                    str_mapping[key] = str(value)
            result = await client.mset(str_mapping)
            return bool(result)
        except Exception as e:
            logging.warning(f"Redis MSET操作失败: {e}")
            return False

class RedisDistributedLock:
    """Redis分布式锁"""
    
    def __init__(self, space: RedisSpaceEnum, lock_key: str, lock_value: str = None, timeout: int = 10, blocking_timeout: int = 1):
        self.space = space
        self.lock_key = lock_key
        self.lock_value = lock_value or str(uuid.uuid4())
        self.timeout = timeout
        self.blocking_timeout = blocking_timeout
        self._acquired = False
    
    async def acquire(self) -> bool:
        """获取锁"""
        try:
            # 清理可能存在的旧锁
            redis_client = REDIS_CONN
            await redis_client.delete_if_equal(self.lock_key, self.lock_value, self.space)
            
            # 尝试获取锁
            client = redis_client._connet_pool.get_client(self.space)
            result = await client.set(
                self.lock_key, 
                self.lock_value, 
                nx=True, 
                ex=self.timeout
            )
            self._acquired = bool(result)
            return self._acquired
        except Exception as e:
            logging.error(f"获取分布式锁失败 {self.lock_key}: {e}")
            return False
    
    async def spin_acquire(self, max_wait_time: int = 30) -> bool:
        """异步自旋获取锁
        
        Args:
            max_wait_time: 最大等待时间（秒），默认30秒
        """
        try:
            # 清理可能存在的旧锁
            redis_client = REDIS_CONN
            await redis_client.delete_if_equal(self.lock_key, self.lock_value, self.space)
            
            start_time = time.time()
            client = redis_client._connet_pool.get_client(self.space)
            
            # 自旋等待获取锁
            while True:
                result = await client.set(
                    self.lock_key, 
                    self.lock_value, 
                    nx=True, 
                    ex=self.timeout
                )
                if result:
                    self._acquired = True
                    return True
                
                # 检查是否超时
                elapsed_time = time.time() - start_time
                if elapsed_time >= max_wait_time:
                    logging.warning(f"获取分布式锁超时 {self.lock_key}, 等待时间: {elapsed_time:.2f}秒")
                    return False
                
                # 等待一段时间后重试
                await asyncio.sleep(0.1)  # 100ms间隔
                
        except Exception as e:
            logging.error(f"异步获取分布式锁失败 {self.lock_key}: {e}")
            return False
    
    async def release(self) -> bool:
        """释放锁"""
        try:
            if self._acquired:
                redis_client = REDIS_CONN
                result = await redis_client.delete_if_equal(self.lock_key, self.lock_value, self.space)
                self._acquired = False
                return result
            return True
        except Exception as e:
            logging.error(f"释放分布式锁失败 {self.lock_key}: {e}")
            return False

# 全局Redis客户端实例 - 提供便捷的静态方法调用
REDIS_CONN = RedisClient()

