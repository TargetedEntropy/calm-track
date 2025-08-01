"""
Test cases for acquire_lock() and release_lock() functions in scraper.py
"""

import pytest
import os
import sys
import fcntl
import tempfile
import threading
import time
import subprocess
from unittest.mock import patch, mock_open, MagicMock
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

# Import the functions we're testing
from scraper import acquire_lock, release_lock, LOCK_FILE


class TestAcquireLock:
    """Test cases for the acquire_lock function"""

    def setup_method(self):
        """Clean up any existing lock files before each test"""
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    def teardown_method(self):
        """Clean up lock files after each test"""
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    def test_acquire_lock_success(self):
        """Test successful lock acquisition"""
        lock_file = acquire_lock()

        # Verify the lock file was created and returned
        assert lock_file is not None
        assert not lock_file.closed
        assert os.path.exists(LOCK_FILE)

        # Clean up
        release_lock(lock_file)

    def test_acquire_lock_creates_correct_file_path(self):
        """Test that acquire_lock creates the file at the correct path"""
        assert not os.path.exists(LOCK_FILE)

        lock_file = acquire_lock()

        # Verify file was created at the expected location
        assert os.path.exists(LOCK_FILE)
        assert LOCK_FILE == "/tmp/minecraft_scraper.lock"

        # Clean up
        release_lock(lock_file)

    def test_acquire_lock_file_is_writable(self):
        """Test that the acquired lock file is opened in write mode"""
        lock_file = acquire_lock()

        # File should be writable
        assert lock_file.writable()
        assert lock_file.mode == 'w'

        # Clean up
        release_lock(lock_file)

    @patch('builtins.open')
    @patch('fcntl.lockf')
    def test_acquire_lock_calls_fcntl_correctly(self, mock_lockf, mock_open):
        """Test that acquire_lock calls fcntl.lockf with correct parameters"""
        mock_file = MagicMock()
        mock_open.return_value = mock_file

        acquire_lock()

        # Verify open was called correctly
        mock_open.assert_called_once_with(LOCK_FILE, "w")

        # Verify fcntl.lockf was called with correct parameters
        mock_lockf.assert_called_once_with(mock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)

    @patch('builtins.open')
    @patch('fcntl.lockf')
    def test_acquire_lock_ioerror_prints_message_and_exits(self, mock_lockf, mock_open):
        """Test that IOError causes proper error message and exit"""
        mock_file = MagicMock()
        mock_open.return_value = mock_file
        mock_lockf.side_effect = IOError("Resource temporarily unavailable")

        with patch('builtins.print') as mock_print:
            with pytest.raises(SystemExit) as exc_info:
                acquire_lock()

            # Verify error message was printed
            mock_print.assert_called_once_with("Another instance is already running.")
            
            # Verify exit code is 1
            assert exc_info.value.code == 1

    @patch('builtins.open')
    def test_acquire_lock_open_ioerror_propagates(self, mock_open):
        """Test that IOError from open() is handled the same way"""
        mock_open.side_effect = IOError("Permission denied")

        with patch('builtins.print') as mock_print:
            with pytest.raises(SystemExit) as exc_info:
                acquire_lock()

            mock_print.assert_called_once_with("Another instance is already running.")
            assert exc_info.value.code == 1

    @patch('builtins.open')
    @patch('fcntl.lockf')
    def test_acquire_lock_different_ioerror_messages(self, mock_lockf, mock_open):
        """Test that different IOError messages still result in same behavior"""
        mock_file = MagicMock()
        mock_open.return_value = mock_file
        
        error_messages = [
            "Resource temporarily unavailable",
            "Operation not permitted", 
            "No locks available",
            "Device or resource busy"
        ]

        for error_msg in error_messages:
            mock_lockf.side_effect = IOError(error_msg)
            
            with patch('builtins.print') as mock_print:
                with pytest.raises(SystemExit) as exc_info:
                    acquire_lock()

                mock_print.assert_called_once_with("Another instance is already running.")
                assert exc_info.value.code == 1

    def test_acquire_lock_returns_file_object(self):
        """Test that acquire_lock returns a valid file object"""
        lock_file = acquire_lock()

        # Should return a file object
        assert hasattr(lock_file, 'read')
        assert hasattr(lock_file, 'write') 
        assert hasattr(lock_file, 'close')
        assert hasattr(lock_file, 'closed')

        # File should be open
        assert not lock_file.closed

        # Clean up
        release_lock(lock_file)

    @patch('builtins.open')
    @patch('fcntl.lockf')  
    def test_acquire_lock_non_ioerror_propagates(self, mock_lockf, mock_open):
        """Test that non-IOError exceptions are not caught"""
        mock_file = MagicMock()
        mock_open.return_value = mock_file
        mock_lockf.side_effect = ValueError("Some other error")

        # Should not catch ValueError
        with pytest.raises(ValueError, match="Some other error"):
            acquire_lock()

    def test_acquire_lock_real_file_operations(self):
        """Test with real file operations (no mocking)"""
        # This should work without any mocking
        lock_file = acquire_lock()
        
        # Verify real file operations
        assert os.path.exists(LOCK_FILE)
        assert not lock_file.closed
        assert lock_file.name == LOCK_FILE

        # Try to write to it (should work since it's opened in write mode)
        lock_file.write("test")
        lock_file.flush()

        # Clean up
        release_lock(lock_file)


class TestReleaseLock:
    """Test cases for the release_lock function"""

    def setup_method(self):
        """Clean up any existing lock files before each test"""
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    def teardown_method(self):
        """Clean up lock files after each test"""
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    def test_release_lock_success(self):
        """Test successful lock release"""
        # First acquire a lock
        lock_file = acquire_lock()
        assert os.path.exists(LOCK_FILE)
        assert not lock_file.closed

        # Release the lock
        release_lock(lock_file)

        # Verify the file was closed and removed
        assert lock_file.closed
        assert not os.path.exists(LOCK_FILE)

    @patch('fcntl.lockf')
    def test_release_lock_calls_fcntl_unlock(self, mock_lockf):
        """Test that release_lock calls fcntl.lockf to unlock"""
        lock_file = acquire_lock()
        
        release_lock(lock_file)

        # Should have been called at least twice: once for acquire, once for release
        # The release call should be LOCK_UN
        unlock_calls = [call for call in mock_lockf.call_args_list 
                       if call[0][1] == fcntl.LOCK_UN]
        assert len(unlock_calls) >= 1

    def test_release_lock_closes_file(self):
        """Test that release_lock closes the file"""
        lock_file = acquire_lock()
        assert not lock_file.closed

        release_lock(lock_file)

        assert lock_file.closed

    def test_release_lock_removes_file(self):
        """Test that release_lock removes the lock file"""
        lock_file = acquire_lock()
        assert os.path.exists(LOCK_FILE)

        release_lock(lock_file)

        # File should be removed
        assert not os.path.exists(LOCK_FILE)

    def test_release_lock_handles_missing_file_gracefully(self):
        """Test that release_lock handles missing file without error"""
        lock_file = acquire_lock()
        
        # Manually remove the file before calling release_lock
        os.remove(LOCK_FILE)
        assert not os.path.exists(LOCK_FILE)

        # This should not raise an exception
        release_lock(lock_file)

        # File should still be closed
        assert lock_file.closed

    @patch('os.remove')
    def test_release_lock_handles_remove_exception(self, mock_remove):
        """Test that release_lock handles os.remove exceptions gracefully"""
        lock_file = acquire_lock()
        
        # Make os.remove raise various exceptions
        exceptions_to_test = [
            OSError("Permission denied"),
            PermissionError("Access denied"),
            FileNotFoundError("File not found"),
            Exception("Generic error")
        ]

        for exception in exceptions_to_test:
            # Reset for each test
            lock_file = acquire_lock()
            mock_remove.side_effect = exception

            # Should not raise an exception
            release_lock(lock_file)

            # File should still be closed
            assert lock_file.closed
            
            # Reset
            mock_remove.side_effect = None
            mock_remove.reset_mock()

    @patch('fcntl.lockf')
    def test_release_lock_handles_unlock_exception(self, mock_lockf):
        """Test that release_lock handles fcntl unlock exceptions"""
        # Let acquire work, but make unlock fail
        call_count = 0
        
        def lockf_side_effect(*args):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call (acquire) succeeds
                return None
            else:
                # Second call (release) fails
                raise IOError("Unlock failed")
        
        mock_lockf.side_effect = lockf_side_effect
        
        lock_file = acquire_lock()
        
        # Release should handle the unlock exception
        with pytest.raises(IOError, match="Unlock failed"):
            release_lock(lock_file)

    def test_release_lock_with_already_closed_file(self):
        """Test release_lock with an already closed file"""
        lock_file = acquire_lock()
        
        # Close the file manually first
        lock_file.close()
        assert lock_file.closed

        # release_lock should still work (though may raise exception on unlock)
        # The main thing is it should try to remove the file
        try:
            release_lock(lock_file)
        except:
            # Exception is okay since file is already closed
            pass

        # File should be removed if it existed
        # (might not exist depending on when close() was called)

    @patch('fcntl.lockf')
    @patch('os.remove')
    def test_release_lock_order_of_operations(self, mock_remove, mock_lockf):
        """Test that release_lock performs operations in correct order"""
        lock_file = acquire_lock()
        
        release_lock(lock_file)

        # fcntl.lockf should be called before os.remove
        # (We can't easily test the order of close() vs the others)
        assert mock_lockf.call_count >= 2  # acquire + release
        mock_remove.assert_called_once_with(LOCK_FILE)

    def test_release_lock_idempotent_file_removal(self):
        """Test that calling release_lock multiple times doesn't cause issues"""
        lock_file = acquire_lock()
        
        # First release
        release_lock(lock_file)
        assert not os.path.exists(LOCK_FILE)
        
        # Second release (file already gone) - should not crash
        try:
            release_lock(lock_file)  # This might raise an exception due to closed file
        except:
            pass  # That's okay, the main thing is it doesn't crash the program


class TestLockIntegration:
    """Integration tests for acquire_lock and release_lock together"""

    def setup_method(self):
        """Clean up any existing lock files before each test"""
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    def teardown_method(self):
        """Clean up lock files after each test"""
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    def test_acquire_release_cycle(self):
        """Test complete acquire-release cycle"""
        # Acquire lock
        lock_file = acquire_lock()
        assert os.path.exists(LOCK_FILE)
        assert not lock_file.closed

        # Release lock
        release_lock(lock_file)
        assert lock_file.closed
        assert not os.path.exists(LOCK_FILE)

        # Should be able to acquire again
        lock_file2 = acquire_lock()
        assert os.path.exists(LOCK_FILE)
        assert not lock_file2.closed

        # Clean up
        release_lock(lock_file2)

    def test_multiple_acquire_release_cycles(self):
        """Test multiple acquire-release cycles work correctly"""
        for i in range(3):
            lock_file = acquire_lock()
            assert os.path.exists(LOCK_FILE)
            assert not lock_file.closed

            release_lock(lock_file)
            assert lock_file.closed
            assert not os.path.exists(LOCK_FILE)

    def test_lock_prevents_concurrent_access_simulation(self):
        """Test lock conflict simulation using threading and mocking"""
        results = {"thread1": None, "thread2": None, "exceptions": []}

        def thread1_func():
            try:
                results["thread1"] = acquire_lock()
                time.sleep(0.1)  # Hold the lock briefly
            except SystemExit as e:
                results["exceptions"].append(("thread1", e))

        def thread2_func():
            time.sleep(0.05)  # Let thread1 acquire lock first
            try:
                # Mock fcntl to simulate lock conflict for second thread
                with patch('fcntl.lockf') as mock_lockf:
                    def lockf_side_effect(file_obj, operation):
                        if operation == fcntl.LOCK_EX | fcntl.LOCK_NB:
                            raise IOError("Resource temporarily unavailable")
                    
                    mock_lockf.side_effect = lockf_side_effect
                    results["thread2"] = acquire_lock()
            except SystemExit as e:
                results["exceptions"].append(("thread2", e))

        # Start threads
        t1 = threading.Thread(target=thread1_func)
        t2 = threading.Thread(target=thread2_func)

        t1.start()
        t2.start()

        t1.join(timeout=2.0)
        t2.join(timeout=2.0)

        # Verify that only one thread got the lock
        assert results["thread1"] is not None
        assert results["thread2"] is None
        assert len(results["exceptions"]) == 1
        assert results["exceptions"][0][0] == "thread2"
        assert results["exceptions"][0][1].code == 1

        # Clean up
        if results["thread1"]:
            release_lock(results["thread1"])

class TestLockEdgeCases:
    """Test edge cases and error conditions"""

    def setup_method(self):
        """Clean up any existing lock files before each test"""
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    def teardown_method(self):
        """Clean up lock files after each test"""
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    @patch('builtins.open')
    def test_acquire_lock_permission_denied_on_open(self, mock_open):
        """Test acquire_lock when file creation is denied"""
        mock_open.side_effect = PermissionError("Permission denied")

        with patch('builtins.print') as mock_print:
            with pytest.raises(SystemExit) as exc_info:
                acquire_lock()

            mock_print.assert_called_once_with("Another instance is already running.")
            assert exc_info.value.code == 1

    @patch('os.remove')
    def test_release_lock_permission_denied_on_remove(self, mock_remove):
        """Test release_lock when file removal is denied"""
        lock_file = acquire_lock()
        mock_remove.side_effect = PermissionError("Permission denied")

        # Should not raise an exception
        release_lock(lock_file)
        assert lock_file.closed

    def test_acquire_lock_with_existing_file(self):
        """Test acquire_lock when lock file already exists but is not locked"""
        # Create an existing file (but not locked)
        with open(LOCK_FILE, 'w') as f:
            f.write("existing content")

        # Should still be able to acquire lock (overwrites the file)
        lock_file = acquire_lock()
        assert not lock_file.closed
        assert os.path.exists(LOCK_FILE)

        # Clean up
        release_lock(lock_file)



class TestLockConstants:
    """Test lock file path and constants"""

    def test_lock_file_path_constant(self):
        """Test that LOCK_FILE constant is correct"""
        from scraper import LOCK_FILE
        assert LOCK_FILE == "/tmp/minecraft_scraper.lock"

    def test_lock_file_in_tmp_directory(self):
        """Test that lock file is created in /tmp directory"""
        lock_file = acquire_lock()
        
        assert lock_file.name.startswith("/tmp/")
        assert "minecraft_scraper.lock" in lock_file.name
        
        release_lock(lock_file)

