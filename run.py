#!/usr/bin/env python3
"""Run frontend and backend development servers concurrently."""

import os
import signal
import subprocess
import sys
import threading
from datetime import datetime


class Colors:
    """ANSI color codes."""

    CYAN = "\033[36m"
    GREEN = "\033[32m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class ProcessManager:
    """Manages multiple subprocesses with colored, prefixed output."""

    def __init__(self, log_file):
        self.processes = []
        self.log_file = log_file
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

    def stream_output(self, process, color, prefix):
        """Stream output from process with color and prefix."""
        for line in iter(process.stdout.readline, b""):
            if line:
                decoded = line.decode("utf-8").rstrip()
                self.log(decoded, color=color, prefix=prefix)

    def run_process(self, command, cwd, color, prefix):
        """Run a process and stream its output."""
        try:
            self.log(f"Starting: {' '.join(command)}", color=color, prefix=prefix)

            # pylint: disable=consider-using-with
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )
            self.processes.append(process)

            # Stream output in current thread
            self.stream_output(process, color, prefix)

            # Wait for process to complete
            process.wait()
            if process.returncode != 0:
                self.log(
                    f"Process exited with code {process.returncode}",
                    color=color,
                    prefix=prefix,
                )
                self.exit_code = process.returncode
            else:
                self.log("Process exited normally", color=color, prefix=prefix)

            # Signal that a process has exited
            self.shutdown_event.set()

        except Exception as e:
            self.log(f"Error: {e}", color=color, prefix=prefix)
            self.exit_code = 1
            self.shutdown_event.set()

    def start_all(self):
        """Start all development servers."""
        # Clear log file
        with open(self.log_file, "w", encoding="utf-8") as f:
            f.write(f"=== Observarium Dev Log Started at {datetime.now()} ===\n\n")

        # Start server in separate thread
        server_thread = threading.Thread(
            target=self.run_process,
            args=(["make", "dev-server"], ".", Colors.CYAN, "[server]"),
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

    def stop_all(self):
        """Stop all running processes."""
        for process in self.processes:
            if process.poll() is None:  # Still running
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()


def signal_handler(sig, frame):  # pylint: disable=unused-argument
    """Handle Ctrl+C gracefully."""
    print(f"\n{Colors.BOLD}Stopping all processes...{Colors.RESET}")
    manager.shutdown_event.set()


if __name__ == "__main__":
    log_file = "/tmp/observarium.log"
    manager = ProcessManager(log_file)

    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    print(f"{Colors.BOLD}Starting Observarium development servers...{Colors.RESET}")
    print(f"Logging to: {log_file}\n")

    try:
        exit_code = manager.start_all()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n{Colors.BOLD}Stopping all processes...{Colors.RESET}")
        manager.stop_all()
        sys.exit(130)  # Standard exit code for Ctrl+C
