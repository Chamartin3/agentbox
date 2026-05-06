"""Tests for runner profile stats aggregation and queries."""

from __future__ import annotations

import uuid

import pytest
from agentbox.core.data.records import now_iso
from agentbox.core.data.runner_profiles import RunnerProfileCreate
from agentbox.core.data.schema import runs as runs_table
from agentbox.core.data.schema import usage as usage_table


class TestRunnerProfileStats:
    """Test stats aggregation for runner profiles."""

    def test_stats_empty_profile(self, session_store) -> None:
        """Stats for a profile with no runs returns zeroes."""
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p1",
                name="Empty Profile",
                backend="token",
            )
        )

        stats = session_store.runner_profile_stats("p1")
        assert stats.profile_id == "p1"
        assert stats.runs == 0
        assert stats.succeeded == 0
        assert stats.failed == 0
        assert stats.input_tokens == 0
        assert stats.output_tokens == 0
        assert stats.cost_usd is None
        assert stats.avg_duration_ms is None
        assert stats.last_run_at is None

    def test_stats_aggregates_runs(self, session_store) -> None:
        """Stats aggregates runs and usage correctly."""
        # Create two profiles
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p1",
                name="Profile 1",
                backend="token",
            )
        )
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p2",
                name="Profile 2",
                backend="claude_code",
            )
        )

        now = now_iso()

        # Insert runs for p1: 2 ok, 1 error
        with session_store.engine.begin() as conn:
            # Run 1: ok
            run_id_1 = f"run-{uuid.uuid4().hex[:8]}"
            conn.execute(
                runs_table.insert().values(
                    id=run_id_1,
                    agent_id="agent-1",
                    status="ok",
                    input="test input 1",
                    output="test output 1",
                    created_at=now,
                    finished_at=now,
                    runner_profile_id="p1",
                )
            )
            conn.execute(
                usage_table.insert().values(
                    run_id=run_id_1,
                    input_tokens=100,
                    output_tokens=50,
                    cost_usd=0.10,
                )
            )

            # Run 2: ok
            run_id_2 = f"run-{uuid.uuid4().hex[:8]}"
            conn.execute(
                runs_table.insert().values(
                    id=run_id_2,
                    agent_id="agent-1",
                    status="ok",
                    input="test input 2",
                    output="test output 2",
                    created_at=now,
                    finished_at=now,
                    runner_profile_id="p1",
                )
            )
            conn.execute(
                usage_table.insert().values(
                    run_id=run_id_2,
                    input_tokens=200,
                    output_tokens=100,
                    cost_usd=0.20,
                )
            )

            # Run 3: error
            run_id_3 = f"run-{uuid.uuid4().hex[:8]}"
            conn.execute(
                runs_table.insert().values(
                    id=run_id_3,
                    agent_id="agent-1",
                    status="error",
                    input="test input 3",
                    error="Something went wrong",
                    created_at=now,
                    finished_at=now,
                    runner_profile_id="p1",
                )
            )
            conn.execute(
                usage_table.insert().values(
                    run_id=run_id_3,
                    input_tokens=50,
                    output_tokens=0,
                    cost_usd=0.05,
                )
            )

            # Run 4: ok but for p2 (should not be counted)
            run_id_4 = f"run-{uuid.uuid4().hex[:8]}"
            conn.execute(
                runs_table.insert().values(
                    id=run_id_4,
                    agent_id="agent-2",
                    status="ok",
                    input="test input 4",
                    output="test output 4",
                    created_at=now,
                    finished_at=now,
                    runner_profile_id="p2",
                )
            )
            conn.execute(
                usage_table.insert().values(
                    run_id=run_id_4,
                    input_tokens=500,
                    output_tokens=200,
                    cost_usd=0.50,
                )
            )

        # Check stats for p1
        stats = session_store.runner_profile_stats("p1")
        assert stats.profile_id == "p1"
        assert stats.runs == 3
        assert stats.succeeded == 2
        assert stats.failed == 1
        assert stats.input_tokens == 350  # 100 + 200 + 50
        assert stats.output_tokens == 150  # 50 + 100 + 0
        assert stats.cost_usd == pytest.approx(0.35)  # 0.10 + 0.20 + 0.05
        assert stats.last_run_at == now

        # Check stats for p2
        stats_p2 = session_store.runner_profile_stats("p2")
        assert stats_p2.profile_id == "p2"
        assert stats_p2.runs == 1
        assert stats_p2.succeeded == 1
        assert stats_p2.failed == 0
        assert stats_p2.input_tokens == 500
        assert stats_p2.output_tokens == 200
        assert stats_p2.cost_usd == pytest.approx(0.50)

    def test_stats_date_range_filter(self, session_store) -> None:
        """Stats filtered by since/until only counts runs in range."""
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p1",
                name="Profile",
                backend="token",
            )
        )

        # Create runs at different times using ISO format strings
        # (matching the format used by now_iso())
        times = [
            "2025-01-01T10:00:00",  # t1: outside range (2 hours before)
            "2025-01-01T11:00:00",  # t2: inside range (1 hour before)
            "2025-01-01T12:00:00",  # t3: inside range (at base)
            "2025-01-01T13:00:00",  # t4: outside range (1 hour after)
        ]

        with session_store.engine.begin() as conn:
            for i, t in enumerate(times, 1):
                run_id = f"run-{i}"
                status = "ok" if i % 2 == 1 else "error"
                conn.execute(
                    runs_table.insert().values(
                        id=run_id,
                        agent_id="agent-1",
                        status=status,
                        input=f"input {i}",
                        created_at=t,
                        finished_at=t,
                        runner_profile_id="p1",
                    )
                )
                conn.execute(
                    usage_table.insert().values(
                        run_id=run_id,
                        input_tokens=10 * i,
                        output_tokens=5 * i,
                        cost_usd=0.1 * i,
                    )
                )

        # Filter to middle range
        since = "2025-01-01T10:30:00"
        until = "2025-01-01T12:30:00"

        stats = session_store.runner_profile_stats("p1", since=since, until=until)
        assert stats.runs == 2  # Only runs 2 and 3
        assert stats.succeeded == 1  # Run 3
        assert stats.failed == 1  # Run 2
        assert stats.input_tokens == 50  # 20 + 30
        assert stats.output_tokens == 25  # 10 + 15

    def test_list_runner_profile_stats(self, session_store) -> None:
        """list_runner_profile_stats returns stats for all profiles."""
        # Create three profiles
        for i in range(1, 4):
            session_store.create_runner_profile(
                RunnerProfileCreate(
                    id=f"p{i}",
                    name=f"Profile {i}",
                    backend="token",
                )
            )

        now = now_iso()

        # Insert runs
        with session_store.engine.begin() as conn:
            # p1: 2 runs
            for i in range(1, 3):
                run_id = f"p1-run-{i}"
                conn.execute(
                    runs_table.insert().values(
                        id=run_id,
                        agent_id="agent-1",
                        status="ok",
                        input=f"input {i}",
                        created_at=now,
                        finished_at=now,
                        runner_profile_id="p1",
                    )
                )
                conn.execute(
                    usage_table.insert().values(
                        run_id=run_id,
                        input_tokens=100,
                        output_tokens=50,
                        cost_usd=0.10,
                    )
                )

            # p2: 1 run (failed)
            run_id = "p2-run-1"
            conn.execute(
                runs_table.insert().values(
                    id=run_id,
                    agent_id="agent-2",
                    status="error",
                    input="input",
                    created_at=now,
                    finished_at=now,
                    runner_profile_id="p2",
                )
            )
            conn.execute(
                usage_table.insert().values(
                    run_id=run_id,
                    input_tokens=50,
                    output_tokens=0,
                    cost_usd=0.05,
                )
            )

            # p3: no runs

        # List all stats
        all_stats = session_store.list_runner_profile_stats()

        # p3 has no runs, so it won't appear in the list
        assert len(all_stats) == 2

        # Find p1 and p2 in results
        stats_by_id = {s.profile_id: s for s in all_stats}

        assert "p1" in stats_by_id
        p1_stats = stats_by_id["p1"]
        assert p1_stats.runs == 2
        assert p1_stats.succeeded == 2
        assert p1_stats.failed == 0
        assert p1_stats.input_tokens == 200

        assert "p2" in stats_by_id
        p2_stats = stats_by_id["p2"]
        assert p2_stats.runs == 1
        assert p2_stats.succeeded == 0
        assert p2_stats.failed == 1
        assert p2_stats.input_tokens == 50

    def test_stats_with_no_usage_rows(self, session_store) -> None:
        """Stats handle runs without matching usage rows (outer join)."""
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p1",
                name="Profile",
                backend="token",
            )
        )

        now = now_iso()

        # Insert a run without usage
        with session_store.engine.begin() as conn:
            conn.execute(
                runs_table.insert().values(
                    id="run-1",
                    agent_id="agent-1",
                    status="ok",
                    input="test",
                    created_at=now,
                    finished_at=now,
                    runner_profile_id="p1",
                )
            )

        stats = session_store.runner_profile_stats("p1")
        assert stats.runs == 1
        assert stats.succeeded == 1
        assert stats.input_tokens == 0  # No usage row
        assert stats.output_tokens == 0
        assert stats.cost_usd is None

    def test_stats_avg_duration_ms(self, session_store) -> None:
        """Stats calculate average duration correctly."""
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p1",
                name="Profile",
                backend="token",
            )
        )

        with session_store.engine.begin() as conn:
            # Run 1: 1000 ms duration (1 second)
            conn.execute(
                runs_table.insert().values(
                    id="run-1",
                    agent_id="agent-1",
                    status="ok",
                    input="test",
                    created_at="2025-01-01T12:00:00",
                    finished_at="2025-01-01T12:00:01",
                    runner_profile_id="p1",
                )
            )

            # Run 2: 2000 ms duration (2 seconds)
            conn.execute(
                runs_table.insert().values(
                    id="run-2",
                    agent_id="agent-1",
                    status="ok",
                    input="test",
                    created_at="2025-01-01T12:00:02",
                    finished_at="2025-01-01T12:00:04",
                    runner_profile_id="p1",
                )
            )

        stats = session_store.runner_profile_stats("p1")
        assert stats.runs == 2
        # Average should be 1500 ms (but allow some floating point tolerance)
        assert stats.avg_duration_ms is not None
        assert 1400 < stats.avg_duration_ms < 1600

    def test_stats_respects_date_range_in_list(self, session_store) -> None:
        """list_runner_profile_stats also respects since/until filters."""
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p1",
                name="Profile",
                backend="token",
            )
        )

        with session_store.engine.begin() as conn:
            # Runs at different times
            times = [
                "2025-01-01T12:00:00",  # run 1
                "2025-01-01T13:00:00",  # run 2
                "2025-01-01T14:00:00",  # run 3
            ]
            for i, t in enumerate(times, 1):
                run_id = f"run-{i}"
                conn.execute(
                    runs_table.insert().values(
                        id=run_id,
                        agent_id="agent-1",
                        status="ok",
                        input="test",
                        created_at=t,
                        finished_at=t,
                        runner_profile_id="p1",
                    )
                )
                conn.execute(
                    usage_table.insert().values(
                        run_id=run_id,
                        input_tokens=10,
                        output_tokens=5,
                    )
                )

        # Filter to middle hour (13:30 is outside, only 13:00 is inside)
        since = "2025-01-01T12:30:00"
        until = "2025-01-01T13:30:00"

        stats_list = session_store.list_runner_profile_stats(since=since, until=until)
        assert len(stats_list) == 1
        assert stats_list[0].profile_id == "p1"
        assert stats_list[0].runs == 1  # Only run 2 is in range
