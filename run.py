#!/usr/bin/env python3
"""Run frontend and backend development servers concurrently."""

import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime

# Matches the leading level token emitted by the backend's
# `logging.basicConfig(format="%(levelname)s %(name)s: %(message)s")` config
# (see server/local_server.py). Lines that don't match (tracebacks, raw
# print() output, etc.) default to being treated as INFO so nothing important
# is ever silently dropped from the console.
BACKEND_LOG_LEVEL_RE = re.compile(r"^(DEBUG|INFO|WARNING|ERROR|CRITICAL)\b")


class Colors:
    """ANSI color codes."""

    CYAN = "\033[36m"
    GREEN = "\033[32m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class ProcessManager:
    """Manages multiple subprocesses with colored, prefixed output."""

    def __init__(self, log_file, backend_log_file=None):
        self.processes = []
        self.log_file = log_file
        self.backend_log_file = backend_log_file
        self.lock = threading.Lock()
        self.shutdown_event = threading.Event()
        self.exit_code = 0

    def log(self, message, color="", prefix=""):
        """Write message to both stdout and log file."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {prefix} {message}"
        colored_line = f"{color}{log_line}{Colors.RESET}"

        with self.lock:
            # Write colored output to terminal
            print(colored_line, flush=True)
            # Write plain text to log file
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")

    def log_backend(self, message, color="", prefix=""):
        """Write a backend log line to the dedicated backend log file (every
        level, including DEBUG), but only echo it to the console/combined
        dev log when its level is INFO or above."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {prefix} {message}"
        level_match = BACKEND_LOG_LEVEL_RE.match(message)
        level = level_match.group(1) if level_match else "INFO"

        with self.lock:
            if self.backend_log_file:
                with open(self.backend_log_file, "a", encoding="utf-8") as f:
                    f.write(log_line + "\n")
            if level != "DEBUG":
                colored_line = f"{color}{log_line}{Colors.RESET}"
                print(colored_line, flush=True)
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(log_line + "\n")

    def stream_output(self, process, color, prefix, is_backend=False):
        """Stream output from process with color and prefix."""
        emit = self.log_backend if is_backend else self.log
        for line in iter(process.stdout.readline, b""):
            if line:
                decoded = line.decode("utf-8").rstrip()
                emit(decoded, color=color, prefix=prefix)

    def run_process(self, command, cwd, color, prefix, is_backend=False):
        """Run a process and stream its output."""
        emit = self.log_backend if is_backend else self.log
        try:
            emit(f"Starting: {' '.join(command)}", color=color, prefix=prefix)

            # pylint: disable=consider-using-with
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                start_new_session=True,  # gives the child its own process group
            )
            self.processes.append(process)

            # Stream output in current thread
            self.stream_output(process, color, prefix, is_backend=is_backend)

            # Wait for process to complete
            process.wait()
            if process.returncode != 0:
                emit(
                    f"Process exited with code {process.returncode}",
                    color=color,
                    prefix=prefix,
                )
                self.exit_code = process.returncode
            else:
                emit("Process exited normally", color=color, prefix=prefix)

            # Signal that a process has exited
            self.shutdown_event.set()

        except Exception as e:
            emit(f"Error: {e}", color=color, prefix=prefix)
            self.exit_code = 1
            self.shutdown_event.set()

    def start_all(self):
        """Start all development servers."""
        # Clear log files
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(f"=== Observarium Dev Log Started at {datetime.now()} ===\n\n")
        if self.backend_log_file:
            with open(self.backend_log_file, "w", encoding="utf-8") as f:
                f.write(f"=== Observarium Backend Log Started at {datetime.now()} ===\n\n")

        # Start server in separate thread
        server_thread = threading.Thread(
            target=self.run_process,
            args=(["make", "dev-server"], ".", Colors.CYAN, "[server]"),
            kwargs={"is_backend": True},
            daemon=True,
        )
        server_thread.start()

        # Start client in separate thread
        client_thread = threading.Thread(
            target=self.run_process,
            args=(["make", "dev-client"], ".", Colors.GREEN, "[client]"),
            daemon=True,
        )
        client_thread.start()

        # Wait for any process to exit
        self.shutdown_event.wait()

        # Stop all remaining processes
        self.stop_all()

        return self.exit_code

    def _kill_group(self, process, sig):
        """Send signal to the process group, ignoring errors if already gone."""
        try:
            os.killpg(os.getpgid(process.pid), sig)
        except ProcessLookupError:
            pass

    def stop_all(self):
        """Stop all running processes: SIGTERM → wait 3 s → SIGKILL."""
        running = [p for p in self.processes if p.poll() is None]
        for process in running:
            self._kill_group(process, signal.SIGTERM)

        deadline = time.monotonic() + 3
        for process in running:
            remaining = max(0, deadline - time.monotonic())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                self._kill_group(process, signal.SIGKILL)


def signal_handler(sig, frame):  # pylint: disable=unused-argument
    """Handle Ctrl+C gracefully."""
    print(f"\n{Colors.BOLD}Stopping all processes...{Colors.RESET}")
    manager.shutdown_event.set()


if __name__ == "__main__":
    log_file = "/tmp/observarium.log"
    # Path is supplied by the Makefile (BACKEND_LOG_FILE env var), not hardcoded
    # here — see the root Makefile's `dev` target.
    backend_log_file = os.environ.get("BACKEND_LOG_FILE")
    manager = ProcessManager(log_file, backend_log_file=backend_log_file)

    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    # FRONTEND_LOG_FILE isn't used by this script directly — it's inherited by
    # the dev-client subprocess and read there by client/vite.config.mjs,
    # which forwards browser console.* calls into that file. Mentioned here
    # purely for visibility.
    frontend_log_file = os.environ.get("FRONTEND_LOG_FILE")

    print(f"{Colors.BOLD}Starting Observarium development servers...{Colors.RESET}")
    print(f"Logging to: {log_file}")
    if backend_log_file:
        print(f"Backend debug logging to: {backend_log_file}")
    else:
        print(
            f"{Colors.BOLD}Warning: BACKEND_LOG_FILE not set — backend DEBUG logs "
            f"will not be written to a file.{Colors.RESET}"
        )
    if frontend_log_file:
        print(f"Frontend console logging to: {frontend_log_file}")
    else:
        print(
            f"{Colors.BOLD}Warning: FRONTEND_LOG_FILE not set — browser console "
            f"logs will not be written to a file.{Colors.RESET}"
        )
    print()

    try:
        exit_code = manager.start_all()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n{Colors.BOLD}Stopping all processes...{Colors.RESET}")
        manager.stop_all()
        sys.exit(130)  # Standard exit code for Ctrl+C
