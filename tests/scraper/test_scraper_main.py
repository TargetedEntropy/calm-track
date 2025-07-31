"""
Comprehensive test cases for the main() function in scraper.py
"""

import pytest
import asyncio
import json
import sys
import os
from unittest.mock import Mock, patch, AsyncMock, mock_open, MagicMock
from datetime import datetime
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from scraper import main


class TestMainFunction:
    """Test cases for the main() function"""

    @pytest.fixture
    def mock_servers_config(self):
        """Sample server configuration for testing"""
        return [
            {"id": "test1", "name": "Test Server 1", "ip": "127.0.0.1", "port": 25565},
            {"id": "test2", "name": "Test Server 2", "ip": "127.0.0.1", "port": 25566},
        ]

    @pytest.fixture
    def mock_scraping_results(self):
        """Sample scraping results"""
        return [
            {
                "server_id": "test1",
                "player_count": 3,
                "players": ["Player1", "Player2"],
                "success": True,
            },
            {
                "server_id": "test2",
                "player_count": 1,
                "players": ["Player3"],
                "success": True,
            },
        ]

    @pytest.mark.asyncio
    async def test_main_successful_execution(
        self, mock_servers_config, mock_scraping_results
    ):
        """Test successful execution of main function"""
        mock_lock_file = Mock()
        mock_db_session = Mock()

        with patch("scraper.acquire_lock", return_value=mock_lock_file) as mock_acquire:
            with patch("scraper.release_lock") as mock_release:
                with patch("scraper.Base.metadata.create_all") as mock_create_tables:
                    with patch(
                        "scraper.load_servers", return_value=mock_servers_config
                    ) as mock_load:
                        with patch(
                            "scraper.SessionLocal", return_value=mock_db_session
                        ) as mock_session_local:
                            with patch("scraper.init_servers") as mock_init:
                                with patch(
                                    "scraper.scrape_all_servers",
                                    return_value=mock_scraping_results,
                                ) as mock_scrape:
                                    with patch("scraper.save_results") as mock_save:
                                        with patch(
                                            "builtins.print"
                                        ) as mock_print:

                                            await main()

                                            # Verify all steps were called in order
                                            mock_acquire.assert_called_once()
                                            mock_create_tables.assert_called_once()
                                            mock_load.assert_called_once()
                                            mock_session_local.assert_called_once()
                                            mock_init.assert_called_once_with(
                                                mock_db_session, mock_servers_config
                                            )
                                            mock_scrape.assert_called_once_with(
                                                mock_servers_config
                                            )
                                            mock_save.assert_called_once_with(
                                                mock_db_session, mock_scraping_results
                                            )
                                            mock_db_session.close.assert_called_once()
                                            mock_release.assert_called_once_with(
                                                mock_lock_file
                                            )
                                            mock_print.assert_called_once()
                                            assert "Scraping completed" in str(
                                                mock_print.call_args
                                            )

    @pytest.mark.asyncio
    async def test_main_lock_acquisition_failure(self):
        """Test main function when lock acquisition fails"""
        with patch(
            "scraper.acquire_lock", side_effect=SystemExit(1)
        ) as mock_acquire:
            with pytest.raises(SystemExit) as exc_info:
                await main()

            assert exc_info.value.code == 1
            mock_acquire.assert_called_once()

    @pytest.mark.asyncio
    async def test_main_load_servers_failure(self, mock_servers_config):
        """Test main function when loading servers fails"""
        mock_lock_file = Mock()

        with patch("scraper.acquire_lock", return_value=mock_lock_file):
            with patch("scraper.release_lock") as mock_release:
                with patch("scraper.Base.metadata.create_all"):
                    with patch(
                        "scraper.load_servers",
                        side_effect=FileNotFoundError("servers.json not found"),
                    ):
                        with pytest.raises(FileNotFoundError):
                            await main()

                        # Lock should still be released even on failure
                        mock_release.assert_called_once_with(mock_lock_file)

    @pytest.mark.asyncio
    async def test_main_database_initialization_failure(self, mock_servers_config):
        """Test main function when database initialization fails"""
        mock_lock_file = Mock()

        with patch("scraper.acquire_lock", return_value=mock_lock_file):
            with patch("scraper.release_lock") as mock_release:
                with patch(
                    "scraper.Base.metadata.create_all",
                    side_effect=Exception("Database connection failed"),
                ):
                    with pytest.raises(Exception, match="Database connection failed"):
                        await main()

                    # Lock should still be released
                    mock_release.assert_called_once_with(mock_lock_file)

    @pytest.mark.asyncio
    async def test_main_session_creation_failure(self, mock_servers_config):
        """Test main function when database session creation fails"""
        mock_lock_file = Mock()

        with patch("scraper.acquire_lock", return_value=mock_lock_file):
            with patch("scraper.release_lock") as mock_release:
                with patch("scraper.Base.metadata.create_all"):
                    with patch("scraper.load_servers", return_value=mock_servers_config):
                        with patch(
                            "scraper.SessionLocal",
                            side_effect=Exception("Session creation failed"),
                        ):
                            with pytest.raises(
                                Exception, match="Session creation failed"
                            ):
                                await main()

                            mock_release.assert_called_once_with(mock_lock_file)

    @pytest.mark.asyncio
    async def test_main_init_servers_failure(self, mock_servers_config):
        """Test main function when server initialization fails"""
        mock_lock_file = Mock()
        mock_db_session = Mock()

        with patch("scraper.acquire_lock", return_value=mock_lock_file):
            with patch("scraper.release_lock") as mock_release:
                with patch("scraper.Base.metadata.create_all"):
                    with patch("scraper.load_servers", return_value=mock_servers_config):
                        with patch("scraper.SessionLocal", return_value=mock_db_session):
                            with patch(
                                "scraper.init_servers",
                                side_effect=Exception("Server init failed"),
                            ):
                                with pytest.raises(Exception, match="Server init failed"):
                                    await main()

                                # Database session should be closed
                                mock_db_session.close.assert_called_once()
                                mock_release.assert_called_once_with(mock_lock_file)

    @pytest.mark.asyncio
    async def test_main_scraping_failure(self, mock_servers_config):
        """Test main function when scraping fails"""
        mock_lock_file = Mock()
        mock_db_session = Mock()

        with patch("scraper.acquire_lock", return_value=mock_lock_file):
            with patch("scraper.release_lock") as mock_release:
                with patch("scraper.Base.metadata.create_all"):
                    with patch("scraper.load_servers", return_value=mock_servers_config):
                        with patch("scraper.SessionLocal", return_value=mock_db_session):
                            with patch("scraper.init_servers"):
                                with patch(
                                    "scraper.scrape_all_servers",
                                    side_effect=Exception("Scraping failed"),
                                ):
                                    with pytest.raises(Exception, match="Scraping failed"):
                                        await main()

                                    mock_db_session.close.assert_called_once()
                                    mock_release.assert_called_once_with(mock_lock_file)

    @pytest.mark.asyncio
    async def test_main_save_results_failure(
        self, mock_servers_config, mock_scraping_results
    ):
        """Test main function when saving results fails"""
        mock_lock_file = Mock()
        mock_db_session = Mock()

        with patch("scraper.acquire_lock", return_value=mock_lock_file):
            with patch("scraper.release_lock") as mock_release:
                with patch("scraper.Base.metadata.create_all"):
                    with patch("scraper.load_servers", return_value=mock_servers_config):
                        with patch("scraper.SessionLocal", return_value=mock_db_session):
                            with patch("scraper.init_servers"):
                                with patch(
                                    "scraper.scrape_all_servers",
                                    return_value=mock_scraping_results,
                                ):
                                    with patch(
                                        "scraper.save_results",
                                        side_effect=Exception("Save failed"),
                                    ):
                                        with pytest.raises(Exception, match="Save failed"):
                                            await main()

                                        mock_db_session.close.assert_called_once()
                                        mock_release.assert_called_once_with(mock_lock_file)

    @pytest.mark.asyncio
    async def test_main_empty_server_list(self):
        """Test main function with empty server list"""
        mock_lock_file = Mock()
        mock_db_session = Mock()

        with patch("scraper.acquire_lock", return_value=mock_lock_file):
            with patch("scraper.release_lock") as mock_release:
                with patch("scraper.Base.metadata.create_all"):
                    with patch("scraper.load_servers", return_value=[]):
                        with patch("scraper.SessionLocal", return_value=mock_db_session):
                            with patch("scraper.init_servers") as mock_init:
                                with patch(
                                    "scraper.scrape_all_servers", return_value=[]
                                ) as mock_scrape:
                                    with patch("scraper.save_results") as mock_save:
                                        with patch("builtins.print"):

                                            await main()

                                            # Should still call all functions with empty lists
                                            mock_init.assert_called_once_with(
                                                mock_db_session, []
                                            )
                                            mock_scrape.assert_called_once_with([])
                                            mock_save.assert_called_once_with(
                                                mock_db_session, []
                                            )
                                            mock_db_session.close.assert_called_once()
                                            mock_release.assert_called_once_with(
                                                mock_lock_file
                                            )

    @pytest.mark.asyncio
    async def test_main_scraping_returns_mixed_results(self, mock_servers_config):
        """Test main function when scraping returns mixed success/failure results"""
        mock_lock_file = Mock()
        mock_db_session = Mock()

        mixed_results = [
            {
                "server_id": "test1",
                "player_count": 3,
                "players": ["Player1"],
                "success": True,
            },
            {
                "server_id": "test2",
                "player_count": 0,
                "players": [],
                "success": False,
            },  # Failed server
        ]

        with patch("scraper.acquire_lock", return_value=mock_lock_file):
            with patch("scraper.release_lock") as mock_release:
                with patch("scraper.Base.metadata.create_all"):
                    with patch("scraper.load_servers", return_value=mock_servers_config):
                        with patch("scraper.SessionLocal", return_value=mock_db_session):
                            with patch("scraper.init_servers"):
                                with patch(
                                    "scraper.scrape_all_servers",
                                    return_value=mixed_results,
                                ):
                                    with patch("scraper.save_results") as mock_save:
                                        with patch("builtins.print"):

                                            await main()

                                            # Should save mixed results (save_results handles filtering)
                                            mock_save.assert_called_once_with(
                                                mock_db_session, mixed_results
                                            )
                                            mock_release.assert_called_once_with(
                                                mock_lock_file
                                            )


    @pytest.mark.asyncio
    async def test_main_prints_completion_message(
        self, mock_servers_config, mock_scraping_results
    ):
        """Test that main function prints completion message with timestamp"""
        mock_lock_file = Mock()
        mock_db_session = Mock()

        with patch("scraper.acquire_lock", return_value=mock_lock_file):
            with patch("scraper.release_lock"):
                with patch("scraper.Base.metadata.create_all"):
                    with patch("scraper.load_servers", return_value=mock_servers_config):
                        with patch("scraper.SessionLocal", return_value=mock_db_session):
                            with patch("scraper.init_servers"):
                                with patch(
                                    "scraper.scrape_all_servers",
                                    return_value=mock_scraping_results,
                                ):
                                    with patch("scraper.save_results"):
                                        with patch("builtins.print") as mock_print:
                                            with patch(
                                                "scraper.datetime"
                                            ) as mock_datetime:
                                                mock_datetime.now.return_value = datetime(
                                                    2024, 1, 1, 12, 0, 0
                                                )

                                                await main()

                                                # Verify completion message was printed
                                                mock_print.assert_called_once()
                                                call_args = mock_print.call_args[0][0]
                                                assert "Scraping completed at" in call_args
                                                assert "2024-01-01 12:00:00" in call_args

    @pytest.mark.asyncio
    async def test_main_lock_release_on_exception_in_finally(self, mock_servers_config):
        """Test that lock is released even if release_lock() raises an exception"""
        mock_lock_file = Mock()
        mock_db_session = Mock()

        with patch("scraper.acquire_lock", return_value=mock_lock_file):
            with patch(
                "scraper.release_lock", side_effect=Exception("Release failed")
            ) as mock_release:
                with patch("scraper.Base.metadata.create_all"):
                    with patch("scraper.load_servers", return_value=mock_servers_config):
                        with patch("scraper.SessionLocal", return_value=mock_db_session):
                            with patch("scraper.init_servers"):
                                with patch("scraper.scrape_all_servers", return_value=[]):
                                    with patch("scraper.save_results"):
                                        with patch("builtins.print"):

                                            # Should still attempt to release lock
                                            with pytest.raises(
                                                Exception, match="Release failed"
                                            ):
                                                await main()

                                            mock_release.assert_called_once_with(
                                                mock_lock_file
                                            )


class TestMainIntegration:
    """Integration-style tests for main function with real components"""

    @pytest.mark.asyncio
    async def test_main_with_real_file_operations(self, tmp_path):
        """Test main function with real file operations (mocked network calls)"""
        # Create a temporary servers.json file
        servers_config = [
            {"id": "test1", "name": "Test Server 1", "ip": "127.0.0.1", "port": 25565}
        ]
        servers_file = tmp_path / "servers.json"
        servers_file.write_text(json.dumps(servers_config))

        mock_lock_file = Mock()
        mock_db_session = Mock()
        mock_results = [
            {
                "server_id": "test1",
                "player_count": 2,
                "players": ["Player1"],
                "success": True,
            }
        ]

        # Change to the temporary directory
        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            with patch("scraper.acquire_lock", return_value=mock_lock_file):
                with patch("scraper.release_lock"):
                    with patch("scraper.Base.metadata.create_all"):
                        with patch("scraper.SessionLocal", return_value=mock_db_session):
                            with patch("scraper.init_servers"):
                                with patch(
                                    "scraper.scrape_all_servers", return_value=mock_results
                                ):
                                    with patch("scraper.save_results") as mock_save:
                                        with patch("builtins.print"):

                                            await main()

                                            # Verify that the file was actually read
                                            mock_save.assert_called_once_with(
                                                mock_db_session, mock_results
                                            )
        finally:
            os.chdir(original_cwd)

    @pytest.mark.asyncio
    async def test_main_json_decode_error(self, tmp_path):
        """Test main function with malformed JSON file"""
        # Create a malformed JSON file
        servers_file = tmp_path / "servers.json"
        servers_file.write_text("{ invalid json content")

        mock_lock_file = Mock()

        original_cwd = os.getcwd()
        os.chdir(tmp_path)

        try:
            with patch("scraper.acquire_lock", return_value=mock_lock_file):
                with patch("scraper.release_lock") as mock_release:
                    with patch("scraper.Base.metadata.create_all"):

                        with pytest.raises(json.JSONDecodeError):
                            await main()

                        # Lock should still be released
                        mock_release.assert_called_once_with(mock_lock_file)
        finally:
            os.chdir(original_cwd)

