"""Entry point for the Academic Assessment and Reporting Platform V2.1.

Run the program with::

    python main_v2_1.py <command> <config_file> [options]

Available commands: init, marks, report
"""

from assessment_engine.cli import main

if __name__ == "__main__":
    main()