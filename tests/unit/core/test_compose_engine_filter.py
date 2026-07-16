"""_engines(engines=...) narrows recipe loading; None loads all."""

from agentbox.core.engines.backends.recipe_loader import list_recipes
from agentbox.core.workspaces.compose import WorkspaceComposer


def test_engine_filter():
    c = WorkspaceComposer(None)  # _engines never touches the read manager

    all_names = {r.engine for r in c._engines()}
    assert all_names, "no engines installed in test env"

    assert c._engines(engines=()) == (), "empty filter must render nothing"

    one = next(iter(list_recipes()))
    got = c._engines(engines={one})
    assert len(got) == 1 and got[0].engine == one

    # unknown engines are skipped, not errors
    assert c._engines(engines={"does-not-exist"}) == ()
