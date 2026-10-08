# Numbered steps

A procedure the way an assistant writes one: numbered steps, with a command
under some of them and a remark under others. Everything under a number is
indented, and none of it may be settled while the list is still growing.

1. Make a directory for the work and go into it.

   ```sh
   mkdir -p ~/scratch/advtext-demo
   cd ~/scratch/advtext-demo
   ```

2. Create the environment. This is the step with a paragraph of its own under
   the number, indented to sit inside it.

   Read from its own first line, this paragraph would be an ordinary one at the
   margin. It is the two spaces and the number above that make it part of step
   two, and a scanner that cuts the stream at blank lines gets that wrong.

3. Install the package and its development tools.

   ```sh
   python -m venv .venv
   .venv/bin/pip install -e ".[dev]"
   ```

   The fence above is closed, and the step is not: this sentence is still part
   of it.

4. Run the checks, and read the last line of what they print.

   ```
   2897 passed, 7 skipped, 4 xfailed in 150.31s
   ```

5. Open the demo.

   ```sh
   make run
   ```

6. A step with a nested list under it:

   - the first point, which is short;
   - the second point, which runs on long enough to need a second line in a
     pane of ordinary width, so that a nested item wraps as well;
   - the third.

7. Stop.

After the last step the list is one finished block, and this paragraph is the
first thing that is not inside it.
