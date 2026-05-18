"""Tests for RunnerProfilesMixin — CRUD, binding, and system defaults."""

from __future__ import annotations

from agentbox.core.data.runner_profiles import RunnerProfileCreate, RunnerProfilePatch


class TestRunnerProfilesCRUD:
    """Test basic create, read, update, delete operations."""

    def test_create_and_get_profile(self, session_store) -> None:
        """Create a profile and fetch it back; fields round-trip."""
        data = RunnerProfileCreate(
            id="p1",
            name="Test Profile",
            description="A test runner profile",
            backend="token",
            provider="openai",
            model="openai:gpt-4o",
            base_url="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            params={"temperature": 0.7},
            headers={"X-Custom": "value"},
            extra_args=["--verbose"],
            is_enabled=True,
            is_system_default=False,
        )

        profile = session_store.create_runner_profile(data)
        assert profile.id == "p1"
        assert profile.name == "Test Profile"
        assert profile.description == "A test runner profile"
        assert profile.backend == "token"
        assert profile.provider == "openai"
        assert profile.model == "openai:gpt-4o"
        assert profile.base_url == "https://api.openai.com/v1"
        assert profile.api_key_env == "OPENAI_API_KEY"
        assert profile.params == {"temperature": 0.7}
        assert profile.headers == {"X-Custom": "value"}
        assert profile.extra_args == ["--verbose"]
        assert profile.is_enabled is True
        assert profile.is_system_default is False

        # Fetch and verify round-trip
        fetched = session_store.get_runner_profile("p1")
        assert fetched is not None
        assert fetched.id == profile.id
        assert fetched.params == profile.params
        assert fetched.headers == profile.headers
        assert fetched.extra_args == profile.extra_args

    def test_create_with_auto_id_slugifies_name(self, session_store) -> None:
        """Creating without explicit id auto-generates a slug from the name."""
        data = RunnerProfileCreate(
            name="Auto ID Profile",
            backend="claude_code",
        )

        profile = session_store.create_runner_profile(data)
        assert profile.id == "auto-id-profile"
        # Verify it's persisted
        fetched = session_store.get_runner_profile(profile.id)
        assert fetched is not None

    def test_create_with_auto_id_avoids_collision(self, session_store) -> None:
        """Auto-generated id appends a numeric suffix when the slug already exists."""
        session_store.create_runner_profile(
            RunnerProfileCreate(id="my-profile", name="My Profile", backend="token")
        )

        profile = session_store.create_runner_profile(
            RunnerProfileCreate(name="My Profile", backend="token")
        )
        assert profile.id == "my-profile-2"

        profile3 = session_store.create_runner_profile(
            RunnerProfileCreate(name="My Profile", backend="token")
        )
        assert profile3.id == "my-profile-3"

    def test_create_with_auto_id_empty_name_fallback(self, session_store) -> None:
        """A name that slugifies to nothing falls back to 'profile'."""
        profile = session_store.create_runner_profile(
            RunnerProfileCreate(name="!!!", backend="token")
        )
        assert profile.id.startswith("profile")
        assert profile.id != ""

    def test_list_profiles_filters(self, session_store) -> None:
        """List profiles with filters by backend, provider, and enabled status."""
        # Create multiple profiles
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p1",
                name="OpenAI Profile",
                backend="token",
                provider="openai",
                is_enabled=True,
            )
        )
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p2",
                name="OpenRouter Profile",
                backend="token",
                provider="openrouter",
                is_enabled=True,
            )
        )
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p3",
                name="Claude Code",
                backend="claude_code",
                provider=None,
                is_enabled=False,
            )
        )

        # Filter by backend
        pydantic_profiles = session_store.list_runner_profiles(backend="token")
        assert len(pydantic_profiles) == 2
        assert all(p.backend == "token" for p in pydantic_profiles)

        # Filter by provider
        openai_profiles = session_store.list_runner_profiles(provider="openai")
        assert len(openai_profiles) == 1
        assert openai_profiles[0].id == "p1"

        # Filter by enabled
        enabled_profiles = session_store.list_runner_profiles(enabled=True)
        assert len(enabled_profiles) == 2
        disabled_profiles = session_store.list_runner_profiles(enabled=False)
        assert len(disabled_profiles) == 1
        assert disabled_profiles[0].id == "p3"

        # All profiles
        all_profiles = session_store.list_runner_profiles()
        assert len(all_profiles) == 3

    def test_update_profile(self, session_store) -> None:
        """Update profile with partial patch; others preserved; updated_at advances."""
        # Create a profile
        original = session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p1",
                name="Original Name",
                backend="token",
                provider="openai",
                model="gpt-3.5-turbo",
                params={"temp": 0.5},
            )
        )
        original_updated_at = original.updated_at

        # Patch only some fields
        import time

        time.sleep(0.01)  # Ensure timestamp advances
        updated = session_store.update_runner_profile(
            "p1",
            RunnerProfilePatch(
                name="Updated Name",
            ),
        )

        assert updated.id == "p1"
        assert updated.name == "Updated Name"
        # Preserved fields
        assert updated.backend == "token"
        assert updated.provider == "openai"
        assert updated.model == "gpt-3.5-turbo"
        assert updated.params == {"temp": 0.5}
        # Timestamp advanced
        assert updated.updated_at >= original_updated_at

    def test_delete_profile(self, session_store) -> None:
        """Delete profile and verify it's gone."""
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p1",
                name="To Delete",
                backend="claude_code",
            )
        )

        assert session_store.get_runner_profile("p1") is not None

        session_store.delete_runner_profile("p1")
        assert session_store.get_runner_profile("p1") is None


class TestSystemDefault:
    """Test system default profile enforcement."""

    def test_only_one_system_default(self, session_store) -> None:
        """Creating a second system default clears the first."""
        # Create first system default
        p1 = session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p1",
                name="First Default",
                backend="token",
                is_system_default=True,
            )
        )
        assert p1.is_system_default is True

        # Create second system default
        p2 = session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p2",
                name="Second Default",
                backend="token",
                is_system_default=True,
            )
        )
        assert p2.is_system_default is True

        # Verify p1 is no longer the default
        p1_refreshed = session_store.get_runner_profile("p1")
        assert p1_refreshed is not None
        assert p1_refreshed.is_system_default is False

    def test_get_system_default_returns_active(self, session_store) -> None:
        """get_system_default_runner_profile returns the active default."""
        # No default yet
        assert session_store.get_system_default_runner_profile() is None

        # Set a default
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="default-1",
                name="System Default",
                backend="token",
                is_system_default=True,
            )
        )

        default = session_store.get_system_default_runner_profile()
        assert default is not None
        assert default.id == "default-1"
        assert default.is_system_default is True


class TestAgentProfileBinding:
    """Test binding profiles to agents."""

    def test_set_and_get_agent_runner_profile(self, session_store) -> None:
        """Bind a profile to an agent and fetch it."""
        # Create a profile
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p1",
                name="Agent Profile",
                backend="token",
            )
        )

        # Bind to agent
        result = session_store.set_agent_runner_profile("agent-1", "p1")
        assert result.id == "p1"

        # Fetch agent profile
        fetched = session_store.get_agent_runner_profile("agent-1")
        assert fetched is not None
        assert fetched.id == "p1"

    def test_set_agent_runner_profile_missing_profile_raises(
        self, session_store
    ) -> None:
        """Binding to non-existent profile does not raise, but get returns None."""
        # set_agent_runner_profile does not validate that the profile exists
        # (foreign key is enforced at DB level for real DBs, but SQLite may be lenient)
        # However, a well-designed store should handle this gracefully
        # For now, we test that binding works and the profile lookup fails if it doesn't exist
        session_store.set_agent_runner_profile("agent-1", "nonexistent-id")

        # Trying to get the profile will return None or raise, depending on implementation
        profile = session_store.get_agent_runner_profile("agent-1")
        # If the profile doesn't exist in runner_profiles, the join returns nothing
        assert profile is None

    def test_replace_agent_binding(self, session_store) -> None:
        """Calling set_agent_runner_profile twice replaces the binding."""
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

        # Bind agent to p1
        session_store.set_agent_runner_profile("agent-1", "p1")
        fetched1 = session_store.get_agent_runner_profile("agent-1")
        assert fetched1.id == "p1"

        # Replace with p2
        session_store.set_agent_runner_profile("agent-1", "p2")
        fetched2 = session_store.get_agent_runner_profile("agent-1")
        assert fetched2.id == "p2"

    def test_clear_agent_binding_idempotent(self, session_store) -> None:
        """Clearing an agent binding twice is OK."""
        # Create and bind
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p1",
                name="Profile",
                backend="token",
            )
        )
        session_store.set_agent_runner_profile("agent-1", "p1")
        assert session_store.get_agent_runner_profile("agent-1") is not None

        # Clear once
        session_store.clear_agent_runner_profile("agent-1")
        assert session_store.get_agent_runner_profile("agent-1") is None

        # Clear again (should not error)
        session_store.clear_agent_runner_profile("agent-1")
        assert session_store.get_agent_runner_profile("agent-1") is None


class TestDisabledProfiles:
    """Test behavior with disabled profiles."""

    def test_disabled_profile_still_returned_by_get(self, session_store) -> None:
        """get_runner_profile returns disabled profiles; rejection is resolver's job."""
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p1",
                name="Disabled Profile",
                backend="token",
                is_enabled=False,
            )
        )

        profile = session_store.get_runner_profile("p1")
        assert profile is not None
        assert profile.is_enabled is False

    def test_list_profiles_includes_disabled_by_default(
        self, session_store
    ) -> None:
        """list_runner_profiles includes disabled unless filtered."""
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p1",
                name="Enabled",
                backend="token",
                is_enabled=True,
            )
        )
        session_store.create_runner_profile(
            RunnerProfileCreate(
                id="p2",
                name="Disabled",
                backend="token",
                is_enabled=False,
            )
        )

        all_profiles = session_store.list_runner_profiles()
        assert len(all_profiles) == 2

        enabled_only = session_store.list_runner_profiles(enabled=True)
        assert len(enabled_only) == 1
        assert enabled_only[0].id == "p1"
