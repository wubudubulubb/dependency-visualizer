# Dependency Visualizer

A tool to visualize Python package dependencies within a project using `tach` and `networkx`. It provides an interactive GUI built with CustomTkinter and Matplotlib.

All of the project is vibe-coded as a first vibe-code trial. Initial commit, including most of this readme file is completely AI generated (tool: Cursor)
![Screenshot placeholder - replace with actual screenshot]

## Features

*   Select a Python project root directory.
*   Automatically detects `tach.toml` or generates one.
*   Allows customizing file/directory exclusion patterns (using glob syntax).
*   Displays the package dependency graph using Matplotlib.
*   Interactive graph exploration:
    *   **Hover Nodes:** Shows the full module path in a tooltip.
    *   **Single Left-Click:** Selects a node, highlighting its direct dependencies (outgoing arrows, red) and dependents (incoming arrows, blue). Click again or on the background to deselect.
    *   **Double Left-Click:** Explodes a package node to show its internal sub-packages and modules.
    *   **Right-Click:** Deletes a node and its associated connections from the current view.
    *   **Undo (Button / CTRL+Z):** Reverts the last action (explosion or deletion).
    *   **Toolbar:** Use the standard Matplotlib toolbar buttons for panning and zooming.

## Requirements

*   Python 3.8+
*   [Tach](https://github.com/Polyconseil/tach)
*   `customtkinter`, `networkx`, `matplotlib`
*   (Optional but Recommended for better layout) `pygraphviz` (Requires system-level Graphviz installation first)
*   (For Docker usage) Docker installed and an X server available on the host.

## Installation

### From PyPI (Recommended)

Once the package is published to PyPI:

```bash
pip install dependency-visualizer

# To include optional pygraphviz layout support:
# Install Graphviz system libraries first (see https://graphviz.org/download/)
pip install dependency-visualizer[viz]
```

### From Source

1.  Clone this repository:
    ```bash
    git clone https://github.com/wubudubulubb/dependency-visualizer.git # Or your repo URL
    cd dependency-visualizer
    ```
2.  Install dependencies:
    ```bash
    # Install base dependencies
    pip install .
    # Or, to include optional pygraphviz layout support:
    # Install Graphviz system libraries first (see https://graphviz.org/download/)
    # pip install .[viz]
    ```

## Usage

### After PyPI Installation

Simply run the command in your terminal:

```bash
depviz
```

### Running with Docker

Using Docker allows you to run the application in a containerized environment. You will need to configure X server access from your host machine to display the GUI.

1.  **Build the Docker image:**
    ```bash
    docker build -t dependency-visualizer .
    ```

2.  **Run the container (Example for Linux/macOS with X server):**

    *   **Allow connections from local Docker container (run on host):**
        ```bash
        xhost +local:docker
        ```
        *(Note: This is permissive; more secure methods exist depending on your setup.)*

    *   **Run the Docker container:**
        ```bash
        docker run -it --rm \
               -e DISPLAY=$DISPLAY \
               -v /tmp/.X11-unix:/tmp/.X11-unix \
               dependency-visualizer
        ```
        *   `-it`: Interactive terminal.
        *   `--rm`: Remove container when it exits.
        *   `-e DISPLAY=$DISPLAY`: Passes your host's display environment variable.
        *   `-v /tmp/.X11-unix:/tmp/.X11-unix`: Mounts the X server socket.

    *   **(Alternative for some systems, especially Wayland):** You might need different volume mounts or environment variables like `-e WAYLAND_DISPLAY=$WAYLAND_DISPLAY -v $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY:/tmp/$WAYLAND_DISPLAY`.

    *   **(Windows with WSL and an X Server like VcXsrv/X410):** Configuration varies. You typically need to configure the X server to allow connections and set the `DISPLAY` variable within WSL (often `export DISPLAY=$(cat /etc/resolv.conf | grep nameserver | awk '{print $2; exit;}'):0.0` or similar). Then run the `docker run` command, potentially adjusting the `DISPLAY` variable passed.

3.  **Using the Application (in Docker):** The GUI should appear. Use it as normal. You may need to grant file access if selecting projects outside the container (consider using Docker volumes `-v /path/to/your/projects:/projects` and selecting `/projects` inside the app).

### Running Directly from Source

```bash
python src/dependency_visualizer/main.py
```

Then:

1.  Click "Select Project Root" to choose your Python project directory.
2.  Optionally adjust the "Exclude Patterns".
3.  Click "Load / Refresh" to generate and display the graph.
4.  Interact with the graph using the mouse actions described in Features.

## License

MIT License *(Assuming MIT - update if different)*