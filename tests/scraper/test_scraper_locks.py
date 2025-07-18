import pytest
import os
import sys
import fcntl
import tempfile
import threading
import time
import subprocess
from unittest.mock import patch, mock_open, MagicMock
from io import StringIO

# Constants for testing - match the original exactly
LOCK_FILE = "/tmp/minecraft_scraper.lock"


# The EXACT functions from your scraper.py (no modifications)
def acquire_lock():
    """Prevent multiple instances from running simultaneously"""
    try:
        lock_file = open(LOCK_FILE, "w")
        fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except IOError:
        print("Another instance is already running.")
        sys.exit(1)


def release_lock(lock_file):
    """Release the lock file"""
    fcntl.lockf(lock_file, fcntl.LOCK_UN)
    lock_file.close()
    try:
        os.remove(LOCK_FILE)
    except:
        pass


class TestAcquireLock:
    """Test cases for the acquire_lock function"""

    def setup_method(self):
        """Clean up any existing test lock files before each test"""
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    def teardown_method(self):
        """Clean up test lock files after each test"""
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

    def test_acquire_lock_creates_file(self):
        """Test that acquire_lock creates the lock file"""
        # Ensure file doesn't exist initially
        assert not os.path.exists(LOCK_FILE)

        lock_file = acquire_lock()

        # Verify file was created
        assert os.path.exists(LOCK_FILE)

        # Clean up
        release_lock(lock_file)

    def test_acquire_lock_concurrent_access_prevention(self):
        """Test that acquire_lock prevents concurrent access"""
        # Mock the open function and fcntl.lockf to simulate lock conflict
        mock_file = mock_open().return_value

        with patch("builtins.open", return_value=mock_file):
            with patch(
                "fcntl.lockf", side_effect=IOError("Resource temporarily unavailable")
            ):
                with patch("builtins.print") as mock_print:
                    with pytest.raises(SystemExit) as exc_info:
                        acquire_lock()

                    # Verify it exits with code 1 and prints error message
                    assert exc_info.value.code == 1
                    mock_print.assert_called_once_with(
                        "Another instance is already running."
                    )

    def test_acquire_lock_prints_error_message(self):
        """Test that acquire_lock prints error message when lock is already held"""
        # Mock fcntl.lockf to raise IOError (simulating lock conflict)
        with patch(
            "fcntl.lockf", side_effect=IOError("Resource temporarily unavailable")
        ):
            with patch("builtins.print") as mock_print:
                with pytest.raises(SystemExit) as exc_info:
                    acquire_lock()

                mock_print.assert_called_once_with(
                    "Another instance is already running."
                )
                assert exc_info.value.code == 1

    def test_acquire_lock_threading_scenario(self):
        """Test acquire_lock behavior with threading and mocking"""
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
                with patch(
                    "fcntl.lockf",
                    side_effect=IOError("Resource temporarily unavailable"),
                ):
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


class TestReleaseLock:
    """Test cases for the release_lock function"""

    def setup_method(self):
        """Clean up any existing test lock files before each test"""
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    def teardown_method(self):
        """Clean up test lock files after each test"""
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

    def test_release_lock_removes_file(self):
        """Test that release_lock removes the lock file"""
        lock_file = acquire_lock()
        assert os.path.exists(LOCK_FILE)

        release_lock(lock_file)

        # File should be removed
        assert not os.path.exists(LOCK_FILE)

    def test_release_lock_handles_missing_file(self):
        """Test that release_lock handles missing file gracefully"""
        lock_file = acquire_lock()

        # Manually remove the file before calling release_lock
        os.remove(LOCK_FILE)

        # This should not raise an exception
        release_lock(lock_file)

        # File should still be closed
        assert lock_file.closed

    def test_release_lock_handles_permission_error(self):
        """Test that release_lock handles permission errors gracefully"""
        lock_file = acquire_lock()

        # Mock os.remove to raise a permission error
        with patch("os.remove", side_effect=PermissionError("Permission denied")):
            # This should not raise an exception
            release_lock(lock_file)

        # File should still be closed
        assert lock_file.closed

    def test_release_lock_handles_os_error(self):
        """Test that release_lock handles various OS errors gracefully"""
        lock_file = acquire_lock()

        # Mock os.remove to raise an OSError
        with patch("os.remove", side_effect=OSError("Some OS error")):
            # This should not raise an exception
            release_lock(lock_file)

        # File should still be closed
        assert lock_file.closed

    def test_acquire_lock_file_already_locked_simulation(self):
        """Test acquire_lock when fcntl reports lock conflict"""
        # This is the most reliable way to test lock conflicts
        # We mock fcntl.lockf to raise IOError as it would in a real lock conflict

        mock_file = mock_open().return_value

        with patch("builtins.open", return_value=mock_file):
            with patch(
                "fcntl.lockf", side_effect=IOError("Resource temporarily unavailable")
            ):
                with patch("builtins.print") as mock_print:
                    with pytest.raises(SystemExit) as exc_info:
                        acquire_lock()  # No parameters for the original function

                    mock_print.assert_called_once_with(
                        "Another instance is already running."
                    )
                    assert exc_info.value.code == 1


class TestLockIntegration:
    """Integration tests for lock acquire and release together"""

    def setup_method(self):
        """Clean up any existing test lock files before each test"""
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    def teardown_method(self):
        """Clean up test lock files after each test"""
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
        """Test multiple acquire-release cycles"""
        for i in range(3):
            lock_file = acquire_lock()
            assert os.path.exists(LOCK_FILE)

            release_lock(lock_file)
            assert not os.path.exists(LOCK_FILE)

    def test_lock_prevents_concurrent_access_after_release(self):
        """Test that after releasing a lock, another process can acquire it"""
        # First process acquires and releases lock
        lock_file1 = acquire_lock()
        release_lock(lock_file1)

        # Second process should be able to acquire lock
        lock_file2 = acquire_lock()
        assert lock_file2 is not None
        assert os.path.exists(LOCK_FILE)

        # Clean up
        release_lock(lock_file2)

    def test_basic_lock_functionality_with_mock_conflict(self):
        """Test basic lock functionality and simulated conflict"""
        # First, test normal operation
        lock_file = acquire_lock()
        assert lock_file is not None
        assert os.path.exists(LOCK_FILE)

        release_lock(lock_file)
        assert lock_file.closed
        assert not os.path.exists(LOCK_FILE)

        # Now test conflict scenario with mocking
        with patch(
            "fcntl.lockf", side_effect=IOError("Resource temporarily unavailable")
        ):
            with patch("builtins.print") as mock_print:
                with pytest.raises(SystemExit) as exc_info:
                    acquire_lock()

                mock_print.assert_called_once_with(
                    "Another instance is already running."
                )
                assert exc_info.value.code == 1


class TestLockEdgeCases:
    """Test edge cases and error conditions"""

    def setup_method(self):
        """Clean up any existing test lock files before each test"""
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    def teardown_method(self):
        """Clean up test lock files after each test"""
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    def test_acquire_lock_with_readonly_directory(self):
        """Test acquire_lock when directory is read-only"""
        # Since the original function uses a hardcoded path, we need to mock open
        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            with patch("builtins.print") as mock_print:
                with pytest.raises(SystemExit) as exc_info:
                    acquire_lock()

                # The function catches IOError, not PermissionError, so it will re-raise
                # Let's test the actual behavior - PermissionError should not be caught

        # Actually, let's test what happens when open succeeds but fcntl fails due to permissions
        mock_file = mock_open().return_value
        with patch("builtins.open", return_value=mock_file):
            with patch("fcntl.lockf", side_effect=IOError("Operation not permitted")):
                with patch("builtins.print") as mock_print:
                    with pytest.raises(SystemExit) as exc_info:
                        acquire_lock()

                    mock_print.assert_called_once_with(
                        "Another instance is already running."
                    )
                    assert exc_info.value.code == 1

    @patch("fcntl.lockf")
    def test_acquire_lock_fcntl_error(self, mock_lockf):
        """Test acquire_lock when fcntl.lockf raises an error"""
        mock_lockf.side_effect = IOError("Lock failed")

        with patch("builtins.print") as mock_print:
            with pytest.raises(SystemExit) as exc_info:
                acquire_lock()

            mock_print.assert_called_once_with("Another instance is already running.")
            assert exc_info.value.code == 1

    @patch("fcntl.lockf")
    def test_release_lock_fcntl_error(self, mock_lockf):
        """Test release_lock when fcntl.lockf raises an error during unlock"""
        # First acquire a lock normally
        lock_file = acquire_lock()

        # Make fcntl.lockf raise an error during unlock
        mock_lockf.side_effect = IOError("Unlock failed")

        # This should still complete without raising an exception
        # because the fcntl unlock error isn't caught, but the file operations should still work
        with pytest.raises(IOError):
            release_lock(lock_file)


class TestRealFileLockBehavior:
    """Test with actual file locking (when possible)"""

    def setup_method(self):
        """Clean up any existing test lock files before each test"""
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    def teardown_method(self):
        """Clean up test lock files after each test"""
        try:
            os.remove(LOCK_FILE)
        except FileNotFoundError:
            pass

    def test_real_file_lock_conflict_with_subprocess(self):
        """Test actual file lock conflict using subprocess"""
        # Create a test script that holds a lock
        lock_holder_script = f'''
import fcntl
import time
import sys

try:
    # Create and lock the file (same path as the original function)
    lock_file = open("{LOCK_FILE}", "w")
    fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    print("LOCK_ACQUIRED", flush=True)
    
    # Hold the lock for a while
    time.sleep(1)
    
    # Release the lock
    fcntl.lockf(lock_file, fcntl.LOCK_UN)
    lock_file.close()
    print("LOCK_RELEASED", flush=True)
except Exception as e:
    print(f"ERROR: {{e}}", flush=True)
    sys.exit(1)
'''

        # Create a test script that tries to acquire the same lock
        lock_tester_script = f'''
import sys
import os
import fcntl

# Copy the exact function
LOCK_FILE = "{LOCK_FILE}"

def acquire_lock():
    try:
        lock_file = open(LOCK_FILE, 'w')
        fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except IOError:
        print("Another instance is already running.")
        sys.exit(1)

try:
    lock_file = acquire_lock()
    print("SUCCESS")
    # Clean up
    fcntl.lockf(lock_file, fcntl.LOCK_UN)
    lock_file.close()
    os.remove(LOCK_FILE)
except SystemExit as e:
    print(f"EXIT_CODE:{{e.code}}")
    sys.exit(e.code)
'''

        try:
            # Start the lock holder process
            lock_holder = subprocess.Popen(
                [sys.executable, "-c", lock_holder_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Wait a bit for the lock to be acquired
            time.sleep(0.2)

            # Try to acquire the same lock (should fail)
            lock_tester = subprocess.Popen(
                [sys.executable, "-c", lock_tester_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Wait for both to complete
            tester_out, tester_err = lock_tester.communicate(timeout=2)
            holder_out, holder_err = lock_holder.communicate(timeout=2)

            # The tester should fail with exit code 1
            assert lock_tester.returncode == 1
            assert "EXIT_CODE:1" in tester_out

            # The holder should succeed
            assert lock_holder.returncode == 0
            assert "LOCK_ACQUIRED" in holder_out

        except subprocess.TimeoutExpired:
            # Clean up processes if they hang
            try:
                lock_holder.kill()
                lock_tester.kill()
            except:
                pass
            pytest.fail("Subprocess test timed out")
        finally:
            # Clean up any remaining lock file
            try:
                os.remove(LOCK_FILE)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
