import customtkinter as ctk
from tkinter import filedialog, messagebox
import subprocess
import json
import networkx as nx
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import os
import sys
import tempfile
import shutil

class DependencyVisualizerApp(ctk.CTk):
    """Main application class for the Dependency Visualizer."""

    def __init__(self):
        """Initializes the main application window and widgets."""
        super().__init__()

        self.title("Dependency Visualizer")
        self.geometry("1000x800")

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # --- Top Frame for Controls ---
        self.control_frame = ctk.CTkFrame(self)
        self.control_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.control_frame.grid_columnconfigure(1, weight=1) # Make path entry expand

        self.select_button = ctk.CTkButton(
            self.control_frame, text="Select Project Root", command=self.select_project_root
        )
        self.select_button.grid(row=0, column=0, padx=5, pady=5)

        self.path_entry = ctk.CTkEntry(self.control_frame, placeholder_text="Project Path")
        self.path_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.load_button = ctk.CTkButton(
            self.control_frame, text="Load Dependencies", command=self.load_dependencies
        )
        self.load_button.grid(row=0, column=2, padx=5, pady=5)
        self.load_button.configure(state="disabled") # Disabled until path is selected

        self.deflate_button = ctk.CTkButton(
            self.control_frame, text="Deflate Last", command=self.deflate_last_module
        )
        self.deflate_button.grid(row=0, column=3, padx=5, pady=5)
        self.deflate_button.configure(state="disabled") # Disabled initially

        # --- Main Frame for Graph ---
        self.graph_frame = ctk.CTkFrame(self)
        self.graph_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.graph_frame.grid_columnconfigure(0, weight=1)
        self.graph_frame.grid_rowconfigure(0, weight=1) # Allow canvas to expand

        self.fig, self.ax = plt.subplots(figsize=(8, 6))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.graph_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=0, column=0, sticky="nsew")

        # Add Matplotlib navigation toolbar
        self.toolbar_frame = ctk.CTkFrame(self.graph_frame)
        self.toolbar_frame.grid(row=1, column=0, sticky="ew")
        self.toolbar = NavigationToolbar2Tk(self.canvas, self.toolbar_frame)
        self.toolbar.update()


        # --- State Variables ---
        self.project_root = None
        self.graph = None
        self.node_positions = None
        self.history = [] # To store graph states for undo (explosion/deflation)
        self.selected_node = None

        # --- Bindings ---
        self.canvas.mpl_connect('button_press_event', self.on_click)
        self.canvas.mpl_connect('button_dbl_click_event', self.on_double_click) # TkAgg might use button_press with detail=2
        self.bind('<Control-z>', self.deflate_last_module) # Ctrl+Z for undo

        # Placeholder for double-click detection if button_dbl_click_event doesn't work reliably
        self._last_click_time = 0
        self._click_pos = (0, 0)
        self._double_click_threshold = 0.3 # seconds

    def select_project_root(self):
        """Opens a dialog to select the project root directory."""
        directory = filedialog.askdirectory(title="Select Python Project Root")
        if directory:
            self.project_root = directory
            self.path_entry.delete(0, ctk.END)
            self.path_entry.insert(0, self.project_root)
            self.load_button.configure(state="normal")
            print(f"Selected project root: {self.project_root}")
        else:
            self.load_button.configure(state="disabled")

    def run_tach(self):
        """Runs tach show using a dynamically generated minimal config
           and returns the parsed JSON output."""
        if not self.project_root:
            messagebox.showerror("Error", "No project root selected.")
            return None

        temp_dir = None
        try:
            # --- 1. Detect Source Root ---
            # Prefer 'src' if it exists and looks like a source dir, else use '.'
            potential_src_dir = os.path.join(self.project_root, "src")
            # Basic check: does src exist and is it a directory?
            # A more robust check might look for Python files/packages inside.
            if os.path.isdir(potential_src_dir):
                 # Check if src contains any .py files or directories (potential packages)
                 contains_py_or_pkg = any(
                     item.endswith('.py') or os.path.isdir(os.path.join(potential_src_dir, item))
                     for item in os.listdir(potential_src_dir)
                 )
                 if contains_py_or_pkg:
                      source_root = "src"
                      print("Detected 'src' directory as source root.")
                 else:
                      source_root = "."
                      print("Found 'src' directory, but it seems empty. Using project root '.' as source root.")
            else:
                source_root = "."
                print("No 'src' directory found. Using project root '.' as source root.")


            # --- 2. Create Temporary Config ---
            temp_dir = tempfile.mkdtemp(prefix="depviz_tach_")
            temp_config_path = os.path.join(temp_dir, "pyproject.toml")

            # Define the minimal tach configuration content
            # We map the detected source root to a module covering everything within it.
            # Tach needs a module definition to analyze anything.
            # Note: Tach module paths are relative to the config file's location *unless*
            # the module path is absolute *or* source_roots is set.
            # Simplest approach: Define the module path relative to the project root,
            # and run tach *from* the project root.
            config_content = f"""
[tool.tach]
# Define a single module encompassing the source root
modules = [
    {{ path = "{source_root}" }}
]
# Explicitly set source_roots relative to the project root (where tach runs)
source_roots = ["{source_root}"]

# Optional: Add default exclusion rules if needed
# exclude = ["tests", "docs", ".venv"]
"""

            with open(temp_config_path, "w", encoding="utf-8") as f:
                f.write(config_content)
            print(f"Created temporary tach config at: {temp_config_path}")
            print(f"Using source_root: {source_root}")


            # --- 3. Run Tach with Temporary Config ---
            # Command needs to specify the config file path
            command = [
                sys.executable, "-m", "tach",
                "--config", temp_config_path, # Point tach to our temporary config
                "show", "--format", "json"
            ]
            print(f"Running command: {' '.join(command)} in {self.project_root}")

            # Run tach from the *project root directory* so module paths are relative to it
            result = subprocess.run(
                command,
                cwd=self.project_root, # Crucial: Run from project root
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8'
            )
            print("Tach output received.")
            output = result.stdout
            if output.startswith('﻿'):
                output = output.lstrip('﻿')
            return json.loads(output)

        except FileNotFoundError:
            messagebox.showerror("Error", f"Could not find '{sys.executable} -m tach'. Is tach installed in the environment?")
            return None
        except subprocess.CalledProcessError as e:
            messagebox.showerror(
                "Tach Error",
                f"""Tach failed with exit code {e.returncode}. This might be due to missing '__init__.py' files in your packages, syntax errors, or incorrect source root detection.

Stderr:
{e.stderr}"""
            )
            print(f"Tach stderr:\n{e.stderr}")
            print(f"Tach stdout:\n{e.stdout}")
            # Print the generated config for debugging
            if temp_config_path and os.path.exists(temp_config_path):
                 with open(temp_config_path, "r", encoding="utf-8") as f_cfg:
                      print(f"--- Generated {os.path.basename(temp_config_path)} ---")
                      print(f_cfg.read())
                      print("-------------------------------------")

            return None
        except json.JSONDecodeError as e:
             messagebox.showerror(
                "JSON Error",
                f"""Failed to parse Tach output as JSON:
{e}

Raw output:
{result.stdout[:500]}..."""
            )
             print(f"Failed to parse Tach JSON output: {e}")
             print(f"Raw Tach output:\n{result.stdout}")
             return None
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")
            print(f"Unexpected error running tach: {e}")
            return None
        finally:
            # --- 4. Cleanup Temporary Config ---
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    print(f"Cleaned up temporary directory: {temp_dir}")
                except OSError as e:
                    print(f"Warning: Failed to remove temporary directory {temp_dir}: {e}")

    def build_graph_from_tach(self, tach_data):
        """Builds a networkx graph from the parsed tach JSON data."""
        if not tach_data or 'graph' not in tach_data:
            messagebox.showerror("Error", "Invalid or empty tach data received.")
            return None

        G = nx.DiGraph()
        nodes = tach_data.get('nodes', [])
        edges = tach_data.get('graph', [])

        for node_info in nodes:
             node_id = node_info.get("id")
             if node_id:
                 G.add_node(node_id, **node_info) # Add attributes if needed later

        for edge in edges:
            source = edge.get('source')
            target = edge.get('target')
            if source and target:
                # Tach edge: source -> target means source *depends on* target
                # Requirement: Arrow from dependee (A) to dependency (B) if A imports B
                # So, the edge direction from Tach is correct (dependee -> dependency)
                G.add_edge(source, target)

        print(f"Graph built with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")
        return G

    def draw_graph(self, highlight_node=None):
        """Draws the current graph state on the matplotlib canvas."""
        if not self.graph:
            return

        self.ax.clear()

        # Calculate layout if not already done or if graph changed significantly
        # Re-calculating layout every time can be slow for large graphs
        if self.node_positions is None or set(self.node_positions.keys()) != set(self.graph.nodes()):
             print("Calculating graph layout...")
             try:
                # spring_layout is often good for general graphs
                self.node_positions = nx.spring_layout(self.graph, seed=42)
                print("Layout calculation complete.")
             except Exception as e:
                print(f"Error calculating layout: {e}. Using random layout.")
                self.node_positions = nx.random_layout(self.graph, seed=42)


        node_colors = ['#1f78b4'] * self.graph.number_of_nodes() # Default color
        edge_colors = ['black'] * self.graph.number_of_edges()
        edge_widths = [1.0] * self.graph.number_of_edges()

        # Apply highlighting based on the selected node
        if highlight_node and self.graph.has_node(highlight_node):
            node_list = list(self.graph.nodes())
            edge_list = list(self.graph.edges())
            try:
                node_idx = node_list.index(highlight_node)
                node_colors[node_idx] = 'gray' # Color the selected node itself

                # Highlight dependencies (outgoing edges from selected_node) -> RED
                dependencies = list(self.graph.successors(highlight_node))
                for i, edge in enumerate(edge_list):
                    if edge[0] == highlight_node:
                        edge_colors[i] = 'red'
                        edge_widths[i] = 2.0
                        try:
                            dep_idx = node_list.index(edge[1])
                            node_colors[dep_idx] = 'red'
                        except ValueError: pass # Should not happen if edge exists

                # Highlight dependees (incoming edges to selected_node) -> BLUE
                dependees = list(self.graph.predecessors(highlight_node))
                for i, edge in enumerate(edge_list):
                    if edge[1] == highlight_node:
                        edge_colors[i] = 'blue'
                        edge_widths[i] = 2.0
                        try:
                            dep_idx = node_list.index(edge[0])
                            node_colors[dep_idx] = 'blue'
                        except ValueError: pass # Should not happen if edge exists

            except ValueError:
                print(f"Error finding node {highlight_node} index for highlighting.")
            except Exception as e:
                 print(f"Error during highlighting: {e}")


        print(f"Drawing graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
        nx.draw(
            self.graph,
            pos=self.node_positions,
            ax=self.ax,
            with_labels=True,
            node_size=500, # Adjust size as needed
            node_color=node_colors,
            edge_color=edge_colors,
            width=edge_widths,
            font_size=8,
            font_color='white',
            font_weight='bold',
            arrowsize=15
        )
        self.ax.set_title(f"Project: {os.path.basename(self.project_root or 'N/A')}")
        self.canvas.draw_idle() # Use draw_idle for better responsiveness
        print("Graph drawing complete.")


    def load_dependencies(self):
        """Loads dependencies using tach and displays the graph."""
        print("Loading dependencies...")
        tach_data = self.run_tach()
        if tach_data:
            new_graph = self.build_graph_from_tach(tach_data)
            if new_graph:
                # Reset state for new graph
                self.history = []
                self.graph = new_graph
                self.node_positions = None # Force recalculation of layout
                self.selected_node = None
                self.deflate_button.configure(state="disabled")

                self.draw_graph()
                self._save_history() # Save initial state
            else:
                print("Failed to build graph from tach data.")
        else:
            print("Failed to get tach data.")


    def find_node_at_pos(self, x, y):
        """Finds the graph node closest to the click coordinates (x, y)."""
        if not self.node_positions:
            return None

        min_dist_sq = float('inf')
        closest_node = None

        for node, (nx_pos, ny_pos) in self.node_positions.items():
            # Convert node position (data coords) to display coords for accurate distance check
            disp_x, disp_y = self.ax.transData.transform((nx_pos, ny_pos))
            dist_sq = (disp_x - x)**2 + (disp_y - y)**2
            if dist_sq < min_dist_sq:
                min_dist_sq = dist_sq
                closest_node = node

        # Define a tolerance threshold (e.g., based on node size in display coordinates)
        # This needs refinement - maybe check if click is within node bounds?
        # For now, use a generous pixel distance threshold
        click_tolerance_pixels_sq = 30**2
        if min_dist_sq < click_tolerance_pixels_sq:
             print(f"Click near node: {closest_node}")
             return closest_node
        else:
             print(f"Click not close enough to any node (min_dist_sq={min_dist_sq:.2f})")
             return None


    def on_click(self, event):
        """Handles single clicks on the graph canvas."""
        if event.inaxes != self.ax:
            return

        current_time = event.lastevent.time if hasattr(event.lastevent, 'time') else plt.gcf().canvas.timer.time()
        time_diff = current_time - self._last_click_time
        pos_diff = ((event.x - self._click_pos[0])**2 + (event.y - self._click_pos[1])**2)**0.5

        # Basic double-click detection logic (may need refinement)
        is_double_click = (time_diff < self._double_click_threshold and pos_diff < 5) # Time and position threshold

        self._last_click_time = current_time
        self._click_pos = (event.x, event.y)

        if is_double_click:
             print("Detected double click via on_click logic.")
             self.handle_double_click(event)
             return # Don't process as single click

        # --- Single Click Logic ---
        print(f"Single click detected at ({event.xdata:.2f}, {event.ydata:.2f}) data coords, ({event.x}, {event.y}) display coords")
        clicked_node = self.find_node_at_pos(event.x, event.y)

        if clicked_node:
            if self.selected_node == clicked_node:
                 # Clicked the already selected node - deselect
                 self.selected_node = None
                 print(f"Deselected node: {clicked_node}")
            else:
                self.selected_node = clicked_node
                print(f"Selected node: {self.selected_node}")
            self.draw_graph(highlight_node=self.selected_node)
        else:
             # Clicked outside any node - deselect
             if self.selected_node:
                 self.selected_node = None
                 print("Deselected node (clicked background)")
                 self.draw_graph(highlight_node=self.selected_node)


    def handle_double_click(self, event):
         """Handles double-click events for node explosion."""
         print(f"Double click detected at ({event.xdata:.2f}, {event.ydata:.2f}) data coords, ({event.x}, {event.y}) display coords")
         if event.inaxes != self.ax:
             return

         node_to_explode = self.find_node_at_pos(event.x, event.y)
         if node_to_explode:
             print(f"Attempting to explode node: {node_to_explode}")
             self.explode_module(node_to_explode)


    def on_double_click(self, event):
        """Handles double clicks directly if the backend supports it."""
        # This might not fire reliably with all backends/configs.
        # handle_double_click called from on_click as a fallback.
        print("Direct on_double_click event fired.")
        self.handle_double_click(event)


    def explode_module(self, node_id):
        """Expands a module node to show its direct submodules."""
        if not self.project_root or not self.graph.has_node(node_id):
            return

        print(f"Exploding module: {node_id}")

        # --- 1. Find submodules/subdirectories ---
        module_path_parts = node_id.split('.')
        # Assume node_id corresponds to a directory path relative to a source root within project_root
        # This is a simplification - tach might use different conventions.
        # We need to locate the actual directory corresponding to the node_id.
        # This requires knowing the source roots tach used. Let's assume '.' for now.
        potential_dir = os.path.join(self.project_root, *module_path_parts)

        if not os.path.isdir(potential_dir):
            print(f"Could not find directory for node '{node_id}' at expected path: {potential_dir}")
            # Maybe it's a file module? Check for .py file
            potential_file = potential_dir + ".py"
            if os.path.isfile(potential_file):
                 print(f"Node '{node_id}' corresponds to a file, cannot explode.")
                 messagebox.showinfo("Cannot Explode", f"Module '{node_id}' is a file, not a package/directory.")
                 return
            else:
                 messagebox.showwarning("Cannot Explode", f"Cannot find directory or file for module '{node_id}'.")
                 return

        submodules = []
        try:
            for item in os.listdir(potential_dir):
                item_path = os.path.join(potential_dir, item)
                # Check if it's a directory containing __init__.py (package)
                # or a .py file (module)
                is_pkg = os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, '__init__.py'))
                is_module = os.path.isfile(item_path) and item.endswith('.py') and item != '__init__.py'

                if is_pkg:
                    submodules.append(f"{node_id}.{item}")
                elif is_module:
                    module_name = os.path.splitext(item)[0]
                    submodules.append(f"{node_id}.{module_name}")
        except OSError as e:
             messagebox.showerror("Error", f"Error accessing submodules for '{node_id}': {e}")
             return

        if not submodules:
            print(f"No submodules found for {node_id}")
            messagebox.showinfo("No Submodules", f"No submodules or sub-packages found within '{node_id}'.")
            return

        print(f"Found submodules for {node_id}: {submodules}")

        # --- 2. Modify Graph ---
        self._save_history() # Save state *before* modification

        new_graph = self.graph.copy()
        original_edges = list(new_graph.in_edges(node_id, data=True)) + list(new_graph.out_edges(node_id, data=True))

        # Add new nodes for submodules
        for sub in submodules:
             if not new_graph.has_node(sub): # Avoid adding if somehow exists
                 new_graph.add_node(sub) # Add attributes if needed

        # Rewire edges:
        # Incoming edges to original node -> Connect to relevant submodules? (Complex - requires deeper analysis)
        # --> Simplification: Connect *all* incoming to *all* new submodules for now.
        # Outgoing edges from original node -> Connect from relevant submodules? (Complex)
        # --> Simplification: Connect *all* new submodules to *all* original targets.

        # Connect original predecessors to *all* new submodules
        for u, _, data in new_graph.in_edges(node_id, data=True):
             if u != node_id: # Avoid self-loops if any
                 for sub in submodules:
                     new_graph.add_edge(u, sub, **data)

        # Connect *all* new submodules to original successors
        for _, v, data in new_graph.out_edges(node_id, data=True):
             if v != node_id: # Avoid self-loops
                 for sub in submodules:
                     new_graph.add_edge(sub, v, **data)


        # TODO: Add internal edges *between* submodules if possible?
        # This would ideally require running tach again on the exploded scope,
        # which is complex. For now, we omit internal submodule dependencies.

        # Remove the original node
        new_graph.remove_node(node_id)

        self.graph = new_graph
        # Keep layout somewhat stable? Try removing/adding nodes from/to existing positions.
        # For simplicity now, recalculate layout.
        # self.node_positions.pop(node_id, None) # Remove old node position
        self.node_positions = None # Force recalculation
        self.selected_node = None # Deselect after explosion
        self.deflate_button.configure(state="normal") # Enable deflate

        print(f"Exploded {node_id}. New graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
        self.draw_graph()


    def deflate_last_module(self, event=None):
        """Reverts the last explosion operation."""
        if not self.history:
            print("No history to deflate.")
            return

        print("Deflating last module...")
        last_state = self.history.pop()
        self.graph = last_state['graph']
        self.node_positions = last_state['positions'] # Restore exact previous positions
        self.selected_node = None # Deselect after deflation

        if not self.history: # Disable if history is now empty
             self.deflate_button.configure(state="disabled")

        print(f"Restored graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
        self.draw_graph()

    def _save_history(self):
        """Saves the current graph state to the history stack."""
        if self.graph:
             # Deep copy might be safer if node attributes are mutable, but shallow should work for topology
             graph_copy = self.graph.copy()
             pos_copy = self.node_positions.copy() if self.node_positions else None
             self.history.append({'graph': graph_copy, 'positions': pos_copy})
             print(f"Saved state to history. History size: {len(self.history)}")
             if len(self.history) > 0:
                  self.deflate_button.configure(state="normal")


# --- Entry Point ---
def run_gui():
    """Creates and runs the main application."""
    print("--- run_gui() started ---") # DEBUG
    try:
        # Set appearance mode (optional)
        # ctk.set_appearance_mode("System") # Default
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue") # Default
        print("--- Appearance set ---") # DEBUG

        app = DependencyVisualizerApp()
        print("--- DependencyVisualizerApp initialized ---") # DEBUG

        app.mainloop()
        print("--- mainloop finished ---") # DEBUG

    except Exception as e:
        print(f"--- !!! An error occurred during GUI startup: {e} !!! ---", file=sys.stderr)
        import traceback
        traceback.print_exc() # Print detailed traceback
        # Optionally show an error dialog if tkinter itself didn't fail
        try:
            root = ctk.CTk() # Try to create a minimal window for error
            root.withdraw() # Hide the main window
            messagebox.showerror("Fatal Error", f"Failed to start the application:\n\n{e}")
            root.destroy()
        except Exception as e2:
             print(f"--- Could not even show error dialog: {e2} ---", file=sys.stderr)


if __name__ == "__main__":
    run_gui() 