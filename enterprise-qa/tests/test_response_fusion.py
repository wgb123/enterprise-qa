"""结果融合——端到端集成测试

降级路径（无 LLM）：验证系统不崩溃、输出有基本结构。
具体业务逻辑的验证在 SQL generator / response fusion 的单元测试中。
"""

import os
import tempfile
from pathlib import Path

import pytest

from enterprise_qa.config import Config
from enterprise_qa.db_connector import DBConnector
from enterprise_qa.intent_classifier import classify_intent
from enterprise_qa.kb_retriever import HybridRetriever
from enterprise_qa.response_fusion import ResponseFusion


@pytest.fixture(scope="session")
def real_db():
    """使用真实数据库"""
    base = Path(__file__).resolve().parent.parent.parent
    db_path = base / "enterprise-qa-data" / "enterprise.db"
    if not db_path.exists():
        pytest.skip("数据库文件不存在，请先运行 init_db.sh")
    cfg = Config()
    cfg.database.path = str(db_path)
    cfg.knowledge_base.root_path = str(base / "enterprise-qa-data" / "knowledge")
    cfg.knowledge_base.index_type = "bm25"
    return cfg


@pytest.fixture(scope="session")
def fusion(real_db):
    db = DBConnector(real_db)
    kb = HybridRetriever(real_db)
    return ResponseFusion(db, kb)


class TestResponseFusion:
    """端到端测试——降级路径，验证系统不崩溃且输出有基本结构"""

    def _check_answer(self, answer: str):
        """验证回答的基本结构"""
        assert isinstance(answer, str)
        assert len(answer) > 0
        # 应该有来源标注
        assert "来源" in answer

    def test_email_query(self, fusion):
        """邮箱查询"""
        answer, trace = fusion.answer(classify_intent("张三的邮箱是多少？"))
        self._check_answer(answer)
        assert len(trace) > 0

    def test_department_query(self, fusion):
        """部门查询"""
        answer, trace = fusion.answer(classify_intent("张三在哪个部门？"))
        self._check_answer(answer)
        assert len(trace) > 0

    def test_kb_annual_leave(self, fusion):
        """年假"""
        answer, trace = fusion.answer(classify_intent("年假怎么算？"))
        self._check_answer(answer)
        assert len(trace) > 0

    def test_hybrid_late(self, fusion):
        """迟到"""
        answer, trace = fusion.answer(classify_intent("张三上个月迟到几次？"))
        self._check_answer(answer)
        assert len(trace) > 0

    def test_hybrid_promotion(self, fusion):
        """晋升"""
        answer, trace = fusion.answer(classify_intent("王五符合晋升条件吗？"))
        self._check_answer(answer)
        assert len(trace) > 0

    def test_kb_overtime(self, fusion):
        """加班"""
        answer, trace = fusion.answer(classify_intent("加班有宵夜吗？"))
        self._check_answer(answer)
        assert len(trace) > 0

    def test_cross_table(self, fusion):
        """跨表"""
        answer, trace = fusion.answer(classify_intent("研发部有哪些在研项目？"))
        self._check_answer(answer)
        assert len(trace) > 0

    def test_fuzzy(self, fusion):
        """模糊"""
        answer, trace = fusion.answer(classify_intent("我们团队最近有什么事？"))
        self._check_answer(answer)
        assert len(trace) > 0

    def test_no_result(self, fusion):
        """无结果"""
        answer, trace = fusion.answer(classify_intent("非常不存在的查询内容测试"))
        self._check_answer(answer)
        assert len(trace) > 0

    def test_empty_result(self, fusion):
        """空问题"""
        answer, trace = fusion.answer(classify_intent(""))
        self._check_answer(answer)
        assert len(trace) > 0


class TestStreaming:
    """流式输出测试——验证 answer_stream 的事件序列"""

    def _collect_stream(self, fusion, question: str) -> list[tuple[str, dict]]:
        events: list[tuple[str, dict]] = []
        gen = fusion.answer_stream(classify_intent(question))
        try:
            while True:
                events.append(next(gen))
        except StopIteration:
            pass
        return events

    def test_stream_has_answer_chunk(self, fusion):
        """流式输出包含 answer_chunk 事件"""
        events = self._collect_stream(fusion, "张三的邮箱是多少？")
        event_types = [e[0] for e in events]
        assert "answer_chunk" in event_types, f"缺少 answer_chunk 事件，实际类型: {event_types}"

    def test_stream_ends_with_answer_done(self, fusion):
        """流式输出以 answer_done 结束"""
        events = self._collect_stream(fusion, "研发部有哪些项目？")
        assert events[-1][0] == "answer_done", f"最后事件不是 answer_done: {events[-1]}"

    def test_stream_answer_chunk_has_token(self, fusion):
        """answer_chunk 事件包含 token 字段"""
        events = self._collect_stream(fusion, "年假怎么算？")
        for et, data in events:
            if et == "answer_chunk":
                assert "token" in data
                break
        else:
            pytest.fail("没有 answer_chunk 事件")

    def test_stream_trace_present(self, fusion):
        """流式输出包含 trace 事件"""
        events = self._collect_stream(fusion, "张三在哪个部门？")
        event_types = [e[0] for e in events]
        assert "trace" in event_types, f"缺少 trace 事件: {event_types}"

    def test_stream_token_order(self, fusion):
        """answer_chunk 按顺序出现，且不早于 trace"""
        events = self._collect_stream(fusion, "王五符合晋升条件吗？")
        saw_trace_llm = False
        saw_answer = False
        for et, _ in events:
            if et == "trace":
                saw_trace_llm = True
            if et == "answer_chunk":
                saw_answer = True
                assert saw_trace_llm, "answer_chunk 出现在 trace 之前"
        assert saw_answer, "没有 answer_chunk 事件"

    def test_stream_answer_done_has_sources(self, fusion):
        """answer_done 事件包含 sources 字段"""
        events = self._collect_stream(fusion, "张三的邮箱是多少？")
        for et, data in events:
            if et == "answer_done":
                assert "sources" in data
                break
        else:
            pytest.fail("没有 answer_done 事件")

    def test_stream_consistency_with_answer(self, fusion):
        """流式收集的 token 拼接后 = answer() 返回的文本"""
        events = self._collect_stream(fusion, "迟到怎么扣钱？")
        streamed_tokens = "".join(
            data.get("token", "") for et, data in events if et == "answer_chunk"
        )
        answer_text, _ = fusion.answer(classify_intent("迟到怎么扣钱？"))
        assert streamed_tokens == answer_text, (
            f"流式拼接结果与 answer() 不一致\n"
            f"  流式: {streamed_tokens}\n"
            f"  answer: {answer_text}"
        )
