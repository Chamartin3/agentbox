import pytest
from agentbox.core.tools import registry
from agentbox.core.tools.registry import SharedToolRegistry
from agentbox.core.tools.registry import agent_tool
from pydantic import BaseModel


@pytest.fixture(autouse=True)
def clear_registry():
    SharedToolRegistry.clear()
    yield
    SharedToolRegistry.clear()


class MyIn(BaseModel):
    text: str


class MyOut(BaseModel):
    score: float


def test_decorator_registers_tool():
    @agent_tool(name="test.my_tool", description="A test tool")
    def my_tool(input: MyIn) -> MyOut:
        return MyOut(score=1.0)

    spec = SharedToolRegistry.get("test.my_tool")
    assert spec is not None
    assert spec.name == "test.my_tool"
    assert spec.capability == "test.my_tool"  # defaults to name
    assert spec.input_model is MyIn
    assert spec.output_model is MyOut


def test_custom_capability():
    @agent_tool(name="ns.tool", description="x", capability="ns.cap", tags=["foo"])
    def t(input: MyIn) -> MyOut:
        return MyOut(score=0.0)

    spec = SharedToolRegistry.get("ns.tool")
    assert spec.capability == "ns.cap"
    assert "foo" in spec.tags


def test_duplicate_name_raises():
    @agent_tool(name="dupe.tool", description="first")
    def t1(input: MyIn) -> MyOut:
        return MyOut(score=0.0)

    with pytest.raises(ValueError, match="already registered"):

        @agent_tool(name="dupe.tool", description="second")
        def t2(input: MyIn) -> MyOut:
            return MyOut(score=0.0)


def test_discover_tools_is_idempotent():
    registry._DISCOVERED = False
    registry.discover_tools()
    registry.discover_tools()  # second call must not raise or duplicate
    assert len(SharedToolRegistry.all()) == 0
