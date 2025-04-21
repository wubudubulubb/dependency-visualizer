import customtkinter as ctk
from tkinter import filedialog, messagebox
import subprocess
import json
import networkx as nx
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import os
import sys
import time
import textwrap # For potential future wrapping if needed
try:
    from customtkinter import CTkToolTip # Try standard first
except ImportError:
    try:
        from customtkinter.CTkToolTip import CTkToolTip # Try alternative structure
    except ImportError:
        # If both fail, raise a more informative error or fallback
        print("ERROR: CTkToolTip could not be imported. Please ensure customtkinter is up-to-date (pip install --upgrade customtkinter) and installed correctly.", file=sys.stderr)
        # Optionally, exit or disable the feature
        # sys.exit(1) 
        # For now, let the program continue without the tooltip if import fails
        CTkToolTip = None
try:
    import networkx.drawing.nx_agraph as nx_agraph
    PYGRAPHVIZ_INSTALLED = True
except ImportError:
    PYGRAPHVIZ_INSTALLED = False
    print("\n[Warning] pygraphviz not found. Graph layout will fallback to spring_layout.")
    print("          Install Graphviz system libraries and then run: pip install .[viz]\n")

def truncate_label(label, max_segments=4, join_char='.'):
    """Truncates a label like 'a.b.c.d' to 'a...c.d' if it has max_segments or more."""
    parts = str(label).split(join_char)
    if len(parts) >= max_segments:
        # Keep first segment, add ellipsis, keep last two segments
        return f"{parts[0]}{join_char}...{join_char}{join_char.join(parts[-2:])}"
    else:
        return str(label)

# --- Custom Toolbar ---
class CustomNavigationToolbar(NavigationToolbar2Tk):
    """Custom toolbar that ensures highlighting persists during pan/zoom."""
    def __init__(self, canvas, window, *, app, pack_toolbar=True):
        self.app = app
        self.zooming = False  # Track zoom state
        self.panning = False  # Track pan state
        # Store view limits
        self.view_limits = None
        super().__init__(canvas, window, pack_toolbar=pack_toolbar)

    # --- Override specific action methods --- 

    def pan(self, *args):
        """Override pan action start/toggle."""
        print("CustomToolbar.pan() called")
        self.panning = not self.panning  # Toggle panning state
        if self.panning:
            # Store current view limits when starting pan
            self.view_limits = (self.app.ax.get_xlim(), self.app.ax.get_ylim())
        super().pan(*args)

    def zoom(self, *args):
        """Override zoom action start/toggle."""
        print("CustomToolbar.zoom() called")
        self.zooming = not self.zooming  # Toggle zooming state
        if self.zooming:
            # Store current view limits when starting zoom
            self.view_limits = (self.app.ax.get_xlim(), self.app.ax.get_ylim())
        super().zoom(*args)

    def release_pan(self, event):
        """Override pan action release (mouse button up)."""
        print("CustomToolbar.release_pan() called")
        # Save current limits before they get reset
        current_xlim = self.app.ax.get_xlim()
        current_ylim = self.app.ax.get_ylim()
        
        # Let parent class handle the release
        super().release_pan(event)
        
        if not self.panning:
            # Only redraw when panning is complete (not during pan)
            print("  Redrawing graph after pan release...")
            
            # Store current positions before redrawing
            current_positions = self.app.node_positions.copy() if self.app.node_positions else None
            
            # Redraw with current highlighted node
            self.app.draw_graph(highlight_node=self.app.selected_node, preserve_view=True)
            
            # Restore node positions
            if current_positions:
                self.app.node_positions = current_positions
            
            # Restore limits after redraw
            print(f"  Reapplying limits: x={current_xlim}, y={current_ylim}")
            self.app.ax.set_xlim(current_xlim)
            self.app.ax.set_ylim(current_ylim)
            self.canvas.draw()  # Force canvas update with restored limits

    def release_zoom(self, event):
        """Override zoom action release (mouse button up after drawing zoom box)."""
        print("CustomToolbar.release_zoom() called")
        # Save current limits before they get reset
        current_xlim = self.app.ax.get_xlim()
        current_ylim = self.app.ax.get_ylim()
        
        # Let parent class handle the release
        super().release_zoom(event)
        
        # Get the new limits resulting from the zoom action
        new_xlim = self.app.ax.get_xlim()
        new_ylim = self.app.ax.get_ylim()
        
        # Redraw with current highlighted node
        print("  Redrawing graph after zoom release...")
        
        # Store current positions before redrawing
        current_positions = self.app.node_positions.copy() if self.app.node_positions else None
        
        # Only redraw without resetting view
        self.app.draw_graph(highlight_node=self.app.selected_node, preserve_view=True)
        
        # Restore node positions
        if current_positions:
            self.app.node_positions = current_positions
            
        # Restore the new limits after the redraw
        print(f"  Reapplying zoomed limits: x={new_xlim}, y={new_ylim}")
        self.app.ax.set_xlim(new_xlim)
        self.app.ax.set_ylim(new_ylim)
        self.canvas.draw()  # Force canvas update with restored limits

    # Modify scroll_event override for mouse wheel zoom
    def scroll_event(self, event):
        """Override scroll event to handle mouse wheel zoom with preserved view."""
        print("CustomToolbar.scroll_event() called")
        
        # Save current limits before scroll
        current_xlim = self.app.ax.get_xlim()
        current_ylim = self.app.ax.get_ylim()
        
        # Let the parent handle the actual zoom
        super().scroll_event(event)
        
        # Get new limits after the scroll zoom
        new_xlim = self.app.ax.get_xlim()
        new_ylim = self.app.ax.get_ylim()
        
        # Use the canvas's tk widget to access the .after method
        # Keep the delay for scroll to allow the event to complete
        self.canvas.get_tk_widget().after(
            50, 
            lambda: self._redraw_after_scroll(new_xlim, new_ylim, current_positions=self.app.node_positions.copy())
        ) 

    # Update helper method for delayed redraw
    def _redraw_after_scroll(self, xlim, ylim, current_positions=None):
        """Helper method to redraw the graph with highlights while preserving zoom state."""
        print("CustomToolbar._redraw_after_scroll() executing")
        
        # Redraw while preserving view
        self.app.draw_graph(highlight_node=self.app.selected_node, preserve_view=True)
        
        # Restore node positions if available
        if current_positions:
            self.app.node_positions = current_positions
        
        # Apply the saved limits
        print(f"  Applying saved limits after scroll: x={xlim}, y={ylim}")
        self.app.ax.set_xlim(xlim)
        self.app.ax.set_ylim(ylim)
        
        # Final force draw
        self.canvas.draw()

# --- Main App ---
class DependencyVisualizerApp(ctk.CTk):
    """Main application class for the Dependency Visualizer."""

    def __init__(self):
        """Initializes the main application window and widgets."""
        super().__init__()

        self.title("Dependency Visualizer")
        self.geometry("1000x800")

        # Configure grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1) # Adjust main graph row index

        # --- Top Frame for Controls ---
        self.control_frame = ctk.CTkFrame(self)
        self.control_frame.grid(row=0, column=0, padx=10, pady=(10,0), sticky="new") # Adjusted padding
        self.control_frame.grid_columnconfigure(1, weight=1) # Make path entry expand

        # Row 0: Project Selection
        self.select_button = ctk.CTkButton(
            self.control_frame, text="Select Project Root", command=self.select_project_root
        )
        self.select_button.grid(row=0, column=0, padx=(10,5), pady=5)

        self.path_entry = ctk.CTkEntry(self.control_frame, placeholder_text="Project Path")
        self.path_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        self.load_button = ctk.CTkButton(
            self.control_frame, text="Load / Refresh", command=self.load_dependencies # Renamed button
        )
        self.load_button.grid(row=0, column=2, padx=5, pady=5)
        self.load_button.configure(state="disabled") # Disabled until path is selected

        self.undo_button = ctk.CTkButton(
            self.control_frame, text="Undo Last Action", command=self.undo_last_action # Renamed command
        )
        self.undo_button.grid(row=0, column=3, padx=(5,10), pady=5)
        self.undo_button.configure(state="disabled") # Disabled initially
        
        # Bind hover events for manual tooltip - Use new method names
        self.undo_button.bind("<Enter>", self.show_undo_tooltip)
        self.undo_button.bind("<Leave>", self.hide_undo_tooltip)

        # Row 1: Exclude Patterns
        self.exclude_label = ctk.CTkLabel(self.control_frame, text="Exclude Patterns (Glob, one per line):")
        self.exclude_label.grid(row=1, column=0, padx=(10,5), pady=(5,0), sticky="w")

        self.exclude_textbox = ctk.CTkTextbox(self.control_frame, height=70)
        self.exclude_textbox.grid(row=2, column=0, columnspan=4, padx=10, pady=(0,10), sticky="ew")

        # Default exclude patterns
        default_excludes = [
            "**/__pycache__/", # Cache directories anywhere
            "**/.*/",          # Hidden folders/files anywhere
            "build/",
            "dist/",
            "docs/",
            "**/tests/",       # Test directories anywhere
            "**/test/",
            "**/test_*.py",    # Test files anywhere (prefix)
            "**/*_test.py",    # Test files anywhere (suffix)
            "*.egg-info/",
            "venv/", ".venv/", "env/", ".env/", # Virtual environments (root)
            "**/venv/", "**/.venv/", "**/env/", "**/.env/", # Virtual environments (anywhere)
            "site-packages/",
            "**/site-packages/"
        ]
        self.exclude_textbox.insert("1.0", "\n".join(default_excludes))


        # --- Main Frame for Graph (ROW 3) ---
        self.graph_frame = ctk.CTkFrame(self)
        self.graph_frame.grid(row=3, column=0, padx=5, pady=(2, 5), sticky="nsew") # Reduced pady
        self.graph_frame.grid_columnconfigure(0, weight=1)
        self.graph_frame.grid_rowconfigure(0, weight=1) # Allow canvas to expand

        # Setup matplotlib figure with proper configuration for zooming and panning
        self.fig = plt.figure(figsize=(8, 6))
        self.ax = self.fig.add_subplot(111)
        
        # Use tight layout instead of subplots_adjust
        self.fig.set_tight_layout(True)
        
        # Create the canvas and add to the frame
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.graph_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=0, column=0, sticky="nsew")

        # Add Matplotlib navigation toolbar using the custom class
        self.toolbar_frame = ctk.CTkFrame(self.graph_frame)
        self.toolbar_frame.grid(row=1, column=0, sticky="ew")
        # Instantiate with pack_toolbar=False and manually pack it
        self.toolbar = CustomNavigationToolbar(self.canvas, self.toolbar_frame, app=self, pack_toolbar=False)
        self.toolbar.pack(side=ctk.BOTTOM, fill=ctk.X) # Manually pack the toolbar
        self.toolbar.update()

        # --- Tooltip Label for Nodes (Make it child of canvas_widget) --- 
        self.tooltip_label = ctk.CTkLabel(
            self.canvas_widget, # <<< CHANGE PARENT TO CANVAS WIDGET
            text="", 
            fg_color=("gray85", "gray17"),
            text_color=("black", "white"),
            corner_radius=4,
            padx=5, pady=2
        )
        # Initially hidden

        # --- Tooltip Label for Undo Button ---
        self.undo_tooltip_label = ctk.CTkLabel(
            self.control_frame, 
            text="", 
            fg_color=("gray85", "gray17"),
            text_color=("black", "white"),
            corner_radius=4,
            padx=5, pady=2
        )
        # Initially hidden

        # --- State Variables ---
        self.project_root = None
        self.tach_data = None
        self.graph = None  # NetworkX graph
        self.node_positions = None  # Layout positions
        self.selected_node = None  # Current selected node
        self.hovered_node = None  # Currently hovered node
        self.history = []  # Save states for undo

        # --- Matplotlib Event Bindings ---
        # Use only standard matplotlib events
        self.canvas.mpl_connect('button_press_event', self.on_click)
        self.canvas.mpl_connect('motion_notify_event', self.on_hover)
        
        # Variables to help detect double clicks manually
        self._last_click_time = 0
        self._last_click_event = None
        self._double_click_threshold = 0.3  # seconds
        
        # Bind keyboard shortcuts
        self.bind('<Control-z>', self.undo_last_action)

    def find_python_packages(self, root_dir):
        """Finds directories containing __init__.py (potential packages) within root_dir.

        Args:
            root_dir: The absolute path to the directory to search.

        Returns:
            A list of relative paths (from root_dir) to directories containing __init__.py,
            excluding the root_dir itself.
        """
        if not root_dir or not os.path.isdir(root_dir):
            return []

        package_dirs = []
        root_dir_abs = os.path.abspath(root_dir)

        print(f"Searching for packages (__init__.py) in: {root_dir_abs}")

        for dirpath, dirnames, filenames in os.walk(root_dir_abs, topdown=True):
            # Exclude common virtual environment folders and hidden folders
            # Modify this list as needed
            dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in ('venv', '.venv', 'env', '.env', '__pycache__')]

            if "__init__.py" in filenames:
                # Check if it's the root directory itself
                if os.path.abspath(dirpath) != root_dir_abs:
                    relative_path = os.path.relpath(dirpath, root_dir_abs)
                    # Normalize path separators for consistency
                    package_dirs.append(relative_path.replace('\\', '/'))
                    print(f"  Found package: {relative_path}")

        # Sort for consistent output
        package_dirs.sort()
        print(f"Package search complete. Found {len(package_dirs)} potential packages.")
        return package_dirs

    def select_project_root(self):
        """Opens a dialog to select the project root directory."""
        # Restore title to select project root
        directory = filedialog.askdirectory(title="Select Python Project Root")
        if directory:
            self.project_root = directory # Store the selected directory
            self.path_entry.delete(0, ctk.END)
            self.path_entry.insert(0, self.project_root)
            self.load_button.configure(state="normal")
            print(f"Selected project root: {self.project_root}")
            # Optionally, find packages immediately after selection
            # self.found_packages = self.find_python_packages(self.project_root)
            # print(f"Potential packages found: {self.found_packages}")
        else:
            self.load_button.configure(state="disabled")

    def run_tach(self):
        """Checks for tach.toml, creates/updates it with UI excludes,
           runs tach map, and returns the parsed JSON output."""
        if not self.project_root:
            messagebox.showerror("Error", "No project root selected.")
            return None

        tach_config_path = os.path.join(self.project_root, "tach.toml")

        # --- 1. Get Exclude Patterns from UI --- 
        exclude_text = self.exclude_textbox.get("1.0", "end-1c")
        user_exclude_patterns = [line.strip() for line in exclude_text.splitlines() if line.strip()]
        
        # Format for TOML array - Avoid backslash in f-string expression for < Py3.12
        exclude_toml_lines = []
        for p in user_exclude_patterns:
            # Escape backslashes if needed for TOML strings
            escaped_p = p.replace('\\', '\\\\') 
            exclude_toml_lines.append(f'    "{escaped_p}",')
        exclude_toml_list_str = "\n".join(exclude_toml_lines)
        
        print(f"Using exclude patterns from UI: {user_exclude_patterns}")

        # --- 2. Check for/Create or Update Tach Configuration ---
        # Always write/overwrite tach.toml to ensure current excludes are used
        # If the user had manual changes, they might be lost - a potential improvement point
        print(f"Writing/Updating {tach_config_path} with current exclude patterns.")
        try:
            # Detect Source Root (same logic as before)
            potential_src_dir = os.path.join(self.project_root, "src")
            if os.path.isdir(potential_src_dir) and any(item.endswith('.py') or os.path.isdir(os.path.join(potential_src_dir, item)) for item in os.listdir(potential_src_dir)):
                source_root = "src"
                print("  Using 'src' directory as source root.")
            else:
                source_root = "."
                print("  Using project root '.' as source root.")

            # Generate config content using UI exclude patterns
            config_content = f"""# Auto-generated/Updated by Dependency Visualizer

source_roots = ["{source_root}"]

exclude = [
{exclude_toml_list_str}
]
"""
            print("--- Generated/Updated tach.toml Content ---")
            print(config_content)
            print("-----------------------------------------")
            # Write the config file (overwrite if exists)
            with open(tach_config_path, "w", encoding="utf-8") as f:
                f.write(config_content)
            print(f"  Successfully wrote {tach_config_path}")
        except OSError as e:
             messagebox.showerror("Error", f"Failed to write 'tach.toml' in {self.project_root}:\n{e}")
             print(f"Error writing tach.toml: {e}")
             return None
        except Exception as e:
             messagebox.showerror("Error", f"An unexpected error occurred during config writing: {e}")
             print(f"Unexpected error writing tach.toml: {e}")
             return None

        # --- 3. Run Tach from the selected project root dir ---
        command = [sys.executable, "-m", "tach", "map"]
        print(f"Running command: {' '.join(command)} in {self.project_root}") # Use self.project_root for cwd

        try:
            result = subprocess.run(
                command,
                cwd=self.project_root, # Run from the selected dir
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8'
            )
            print("Tach output received.")
            output = result.stdout
            print("--- Raw Tach Map Output ---")
            print(output)
            print("---------------------------")
            if output.startswith('﻿'):
                output = output.lstrip('﻿')
            # Store the root used by tach (which is self.project_root here)
            self.tach_project_root = self.project_root # Set tach_project_root
            return json.loads(output)

        except FileNotFoundError:
            messagebox.showerror("Error", f"Could not find '{sys.executable} -m tach'. Is tach installed?")
            return None
        except subprocess.CalledProcessError as e:
             # Error should now be more indicative of a real config/project issue
             messagebox.showerror(
                "Tach Error",
                f"""Tach failed with exit code {e.returncode}. Check your tach.toml configuration and project structure (e.g., syntax errors, missing __init__.py).

Stderr:
{e.stderr}"""
            )
             print(f"Tach stderr:\n{e.stderr}")
             print(f"Tach stdout:\n{e.stdout}")
             return None
        except json.JSONDecodeError as e:
              messagebox.showerror(
                 "JSON Error",
                 f"""Failed to parse Tach output (from tach map) as JSON:
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

    def build_graph_from_tach(self, tach_data):
        """Builds a networkx graph of *packages* from the parsed tach map JSON data."""
        # Input format is expected: { "source_file": ["target_file1", ...], ... }
        if not isinstance(tach_data, dict):
            messagebox.showerror("Error", "Invalid tach map data received (expected dict)." + f"\nGot: {type(tach_data)}")
            return None

        print(f"Building package graph from tach map data with {len(tach_data)} entries.")
        G = nx.DiGraph()
        package_dependencies = {} # Store { source_pkg: set(target_pkgs) }
        
        # Track different types of packages
        project_packages = set()  # Internal project packages
        external_packages = set() # External dependencies

        def get_package_from_filepath(filepath):
            """Converts a file path relative to source root to a package name."""
            
            # First, check if this is an external dependency from standard library or site-packages
            normalized_path = filepath.replace('\\', '/')
            
            # Handle external/standard library imports by checking if the path exists
            if not os.path.exists(os.path.join(self.project_root, normalized_path)):
                # This is likely an external dependency
                # Just extract the first part of the path to represent the external package
                parts = normalized_path.split('/')
                if parts and parts[0]:
                    # Return the top-level package name with an "ext:" prefix to mark it as external
                    return f"ext:{parts[0]}"
                return None
                
            # Proceed with normal project package handling
            package_dir = os.path.dirname(normalized_path)
            
            # Convert directory path to package name (dots)
            # If package_dir is empty, it means the file is in the root
            if not package_dir:
                # Maybe return a special name like '<root>' or the filename itself?
                # For now, let's return None for files directly in root.
                # Or, if the filename itself is __init__.py, it represents the parent dir.
                if os.path.basename(normalized_path) == '__init__.py':
                    # This case shouldn't happen often with dirname empty, but conceptually...
                     return None # Or handle root package explicitly if needed
                else:
                    # Treat root-level files as belonging to a conceptual 'root' package? Risky.
                    # Let's try mapping them to their base name without .py
                    base = os.path.basename(normalized_path)
                    if base.endswith('.py'):
                         return base[:-3]
                    return base # Or None? Needs refinement.

            package_name = package_dir.replace('/', '.')
            return package_name

        all_packages = set()
        # Iterate through the map to determine package dependencies
        for source_file, target_files in tach_data.items():
            source_pkg = get_package_from_filepath(source_file)
            if not source_pkg:
                print(f"Warning: Could not determine package for source file '{source_file}'")
                continue

            # Check if this is an external package
            if source_pkg.startswith("ext:"):
                external_packages.add(source_pkg)
            else:
                project_packages.add(source_pkg)
                
            all_packages.add(source_pkg)
            if source_pkg not in package_dependencies:
                package_dependencies[source_pkg] = set()

            for target_file in target_files:
                target_pkg = get_package_from_filepath(target_file)
                if target_pkg:
                    # Check if this is an external package
                    if target_pkg.startswith("ext:"):
                        external_packages.add(target_pkg)
                    else:
                        project_packages.add(target_pkg)
                        
                    all_packages.add(target_pkg)
                    # Add dependency if it's a different package
                    if source_pkg != target_pkg:
                        package_dependencies[source_pkg].add(target_pkg)
                else:
                     print(f"Warning: Could not determine package for target file '{target_file}'")

        # Add nodes for all discovered packages
        for pkg_name in all_packages:
            # Add node attributes for visualization based on package type
            if pkg_name.startswith("ext:"):
                # External package - use different attributes
                G.add_node(pkg_name, is_external=True)
            else:
                # Internal project package
                G.add_node(pkg_name, is_external=False)
                
        print(f"Added {len(all_packages)} package nodes: {sorted(list(all_packages))}")
        print(f"External packages: {sorted(list(external_packages))}")

        # Add edges based on the aggregated package dependencies
        edge_count = 0
        for source_pkg, target_pkgs in package_dependencies.items():
            if G.has_node(source_pkg):
                 for target_pkg in target_pkgs:
                      if G.has_node(target_pkg):
                           G.add_edge(source_pkg, target_pkg)
                           edge_count += 1
                      else:
                           print(f"Warning: Skipping edge to missing target package node '{target_pkg}'")
            else:
                 print(f"Warning: Skipping edges from missing source package node '{source_pkg}'")


        print(f"Package graph built with {G.number_of_nodes()} nodes and {edge_count} edges.")
        # Check for nodes with no connections (might indicate issues or be leaves/roots)
        isolated_nodes = list(nx.isolates(G))
        if isolated_nodes:
            print(f"Warning: Found isolated package nodes: {isolated_nodes}")

        return G

    def draw_graph(self, highlight_node=None, preserve_view=False):
        """Draws the current graph state on the matplotlib canvas with customizations."""
        try:
            if not self.graph: return 
            
            # Store current view limits if preserving view
            if preserve_view:
                current_xlim = self.ax.get_xlim()
                current_ylim = self.ax.get_ylim()
                
            # Setup the plot appearance
            dark_gray = '#505050'
            self.ax.clear()
            self.ax.set_facecolor(dark_gray)
            self.fig.set_facecolor(dark_gray)
            plt.axis('off')
            
            # Calculate layout if needed (avoid recalculating if preserving view)
            if self.node_positions is None or not preserve_view:
                try: 
                    self.node_positions = nx.spring_layout(self.graph, seed=42)
                except Exception as e: 
                    messagebox.showerror("Layout Error", f"Failed to calculate fallback layout: {e}")
                    return
                    
            # Prepare node labels and sizes
            truncated_labels = {node: truncate_label(node, max_segments=4) for node in self.graph.nodes()}
            node_sizes = []
            base_size = 1000
            size_per_char = 100
            min_size = 1000
            max_size = 10000
            
            if self.graph.number_of_nodes() > 0:
                try:
                    for node in self.graph.nodes(): 
                        node_sizes.append(max(min_size, min(max_size, base_size + size_per_char * len(truncated_labels.get(node, ' ')))))
                except Exception as e: 
                    node_sizes = [2500] * self.graph.number_of_nodes()
                    
            if len(node_sizes) != self.graph.number_of_nodes(): 
                node_sizes = [2500] * self.graph.number_of_nodes()
            
            # Define colors
            default_node_color = '#1f78b4'  # Regular project packages
            external_node_color = '#7f007f'  # External dependencies
            default_edge_color = 'black'
            highlight_dep_color = 'red'
            highlight_dee_color = 'blue'
            selected_node_color = 'orange'
            
            # Set node colors based on node type
            node_colors = {}
            for node in self.graph.nodes():
                if self.graph.nodes[node].get('is_external', False):
                    node_colors[node] = external_node_color
                else:
                    node_colors[node] = default_node_color
                    
            edge_colors = {edge: default_edge_color for edge in self.graph.edges()}
            edge_widths = {edge: 1.0 for edge in self.graph.edges()}
            
            # Handle highlighting
            if highlight_node and self.graph.has_node(highlight_node):
                node_colors[highlight_node] = selected_node_color
                for u, v in self.graph.out_edges(highlight_node): 
                    edge = (u, v)
                    edge_colors[edge] = highlight_dep_color
                    edge_widths[edge] = 2.0
                    node_colors[v] = highlight_dep_color
                for u, v in self.graph.in_edges(highlight_node): 
                    edge = (u, v)
                    edge_colors[edge] = highlight_dee_color
                    edge_widths[edge] = 2.0
                    node_colors[u] = highlight_dee_color
            
            # Draw the graph elements
            nx.draw_networkx_edges(
                self.graph, self.node_positions, ax=self.ax, 
                edge_color=[edge_colors.get(edge, default_edge_color) for edge in self.graph.edges()], 
                width=[edge_widths.get(edge, 1.0) for edge in self.graph.edges()], 
                arrowstyle='-|>', arrowsize=15, connectionstyle='arc3,rad=0.1', 
                node_size=node_sizes
            )
            
            nx.draw_networkx_nodes(
                self.graph, self.node_positions, ax=self.ax, 
                node_size=node_sizes, 
                node_color=[node_colors.get(node, default_node_color) for node in self.graph.nodes()], 
                node_shape='o'
            )
            
            # Customize node labels to indicate external packages
            custom_labels = {}
            for node in self.graph.nodes():
                if node.startswith("ext:"):
                    # For external packages, remove the prefix and show just the package name
                    custom_labels[node] = truncate_label(node[4:], max_segments=2)  # Remove "ext:" prefix
                else:
                    custom_labels[node] = truncated_labels[node]
                    
            nx.draw_networkx_labels(
                self.graph, self.node_positions, 
                labels=custom_labels, ax=self.ax, 
                font_size=8, font_color='white', font_weight='bold'
            )
            
            # Set title
            proj_name = os.path.basename(self.project_root) if self.project_root else 'N/A'
            self.ax.set_title(f"Project: {proj_name}")

            # Restore view limits if preserving view
            if preserve_view:
                self.ax.set_xlim(current_xlim)
                self.ax.set_ylim(current_ylim)
                
            # Update the canvas
            self.canvas.draw()
            
        finally:
            pass

    def on_click(self, event):
        """Handles single and double clicks, and right-click for delete."""
        if event.inaxes != self.ax or event.xdata is None or event.ydata is None:
            print("Click ignored (outside axes or null data)")
            return
            
        # Skip normal click processing if we're in zoom or pan mode
        if hasattr(self.toolbar, 'mode') and self.toolbar.mode in ('zoom rect', 'pan/zoom'):
            print(f"Click ignored (toolbar in {self.toolbar.mode} mode)")
            return

        # Get the node under the cursor, if any
        clicked_node = self.find_node_at_pos(event.x, event.y)
        
        # Manual double-click detection
        current_time = time.time()
        is_double_click = False
        
        if (current_time - self._last_click_time < self._double_click_threshold and 
            self._last_click_event is not None and 
            event.button == self._last_click_event.button and
            abs(event.x - self._last_click_event.x) < 5 and 
            abs(event.y - self._last_click_event.y) < 5):
            is_double_click = True
            # Reset time to prevent triple-click detection
            self._last_click_time = 0
            print("Double-click detected (manual detection)")
        else:
            # Store for next time
            self._last_click_time = current_time
            self._last_click_event = event
        
        # --- Right-Click Action (Button 3) --- 
        if event.button == 3:
            print(f"Right-click detected. Node: {clicked_node}")
            if clicked_node:
                self.delete_node(clicked_node)
            return
            
        # --- Double-Click Action (Button 1) --- 
        elif event.button == 1 and is_double_click:
            print(f"Double-click detected on {clicked_node}")
            if clicked_node:
                self.handle_double_click(event)
            return
            
        # --- Single-Click Action (Button 1) --- 
        elif event.button == 1 and not is_double_click:
            print(f"Left-click processing. Node: {clicked_node}")
            
            # Use a short delay to properly distinguish from double-clicks
            # This helps prevent immediate selection followed by explosion on double-click
            def delayed_single_click_action():
                # Skip if this became a double-click during the delay
                if time.time() - self._last_click_time > self._double_click_threshold:
                    if clicked_node:
                        # Toggle selection state
                        if self.selected_node == clicked_node:
                            self.selected_node = None
                            print(f"Node {clicked_node} deselected")
                        else:
                            self.selected_node = clicked_node
                            print(f"Selected node: {self.selected_node}")
                    else:
                        # Clicked background - deselect
                        if self.selected_node:
                            self.selected_node = None
                            print("Deselected node (clicked background)")
                    
                    # Preserve the current view when redrawing after a click
                    current_xlim = self.ax.get_xlim()
                    current_ylim = self.ax.get_ylim()
                    
                    # Redraw with updated selection
                    self.draw_graph(highlight_node=self.selected_node, preserve_view=True)
                    
                    # Restore view limits
                    self.ax.set_xlim(current_xlim)
                    self.ax.set_ylim(current_ylim)
                    self.canvas.draw()
            
            # Schedule the delayed action
            self.after(int(self._double_click_threshold * 1000), delayed_single_click_action)

    def handle_double_click(self, event):
        """Handles double-click events for node explosion."""
        print(f"Handling double click based on event from on_click")
        node_to_explode = self.find_node_at_pos(event.x, event.y)
        if node_to_explode:
            print(f"Attempting to explode node: {node_to_explode}")
            self.explode_module(node_to_explode)

    def explode_module(self, node_id):
        """Expands a package node, adjusts layout, and redraws."""
        # Ensure we have the project root and the node exists
        # Using self.tach_project_root which is set in run_tach after finding tach.toml
        if not hasattr(self, 'tach_project_root') or not self.tach_project_root:
             messagebox.showerror("Error", "Tach project root not determined.")
             return
        if not self.graph or not self.graph.has_node(node_id):
             messagebox.showerror("Error", f"Node '{node_id}' not found in graph.")
             return

        print(f"Exploding package: {node_id}")

        # --- 1. Find submodules/subpackages --- (Now operates on packages)
        package_path_parts = node_id.split('.')
        potential_dir = os.path.join(self.tach_project_root, *package_path_parts)

        if not os.path.isdir(potential_dir):
            # This shouldn't happen if the node represents a package discovered earlier
            # But handle file case just in case get_package_from_filepath produced a file node somehow
            print(f"Warning: Node '{node_id}' does not correspond to a directory: {potential_dir}. Cannot explode.")
            # Maybe check if node_id corresponds to a file path from the original map?
            # For now, just show info and return.
            messagebox.showinfo("Cannot Explode", f"Node '{node_id}' does not map to a known directory.")
            return

        children = [] # Store tuples of (child_name, child_type)
        try:
            for item in os.listdir(potential_dir):
                item_path = os.path.join(potential_dir, item)
                # Check if it's a directory containing __init__.py (sub-package)
                # or a .py file (sub-module)
                is_pkg = os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, '__init__.py'))
                is_module = os.path.isfile(item_path) and item.endswith('.py') and item != '__init__.py'

                child_id = None
                if is_pkg:
                    child_id = f"{node_id}.{item}"
                    children.append((child_id, 'package'))
                elif is_module:
                    module_name = os.path.splitext(item)[0]
                    child_id = f"{node_id}.{module_name}"
                    children.append((child_id, 'module'))

        except OSError as e:
             messagebox.showerror("Error", f"Error accessing sub-items for '{node_id}': {e}")
             return

        if not children:
            print(f"No sub-packages or sub-modules found for {node_id}")
            messagebox.showinfo("No Children", f"No sub-packages or sub-modules found within '{node_id}'.")
            return

        print(f"Found children for {node_id}: {children}")

        # --- 2. Modify Graph --- (Simplified edge rewiring)
        self._save_history() # Save state *before* modification

        new_graph = self.graph.copy()
        new_positions = self.node_positions.copy() if self.node_positions else {}

        # Store original node info
        original_pos = new_positions.pop(node_id, None)
        in_edges = list(new_graph.in_edges(node_id))
        out_edges = list(new_graph.out_edges(node_id))

        # Add new nodes for children & estimate initial positions
        child_nodes = [child_id for child_id, child_type in children]
        for child_id in child_nodes:
             if not new_graph.has_node(child_id):
                 new_graph.add_node(child_id)
                 if original_pos is not None:
                      offset_x = (hash(child_id) % 200 - 100) / 1000.0
                      offset_y = (hash(child_id) % 100 - 50) / 1000.0
                      new_positions[child_id] = (original_pos[0] + offset_x, original_pos[1] + offset_y)
                 else:
                      # Assign a default position if parent had none (shouldn't happen ideally)
                      new_positions[child_id] = (0.5, 0.5) # Center fallback
             else:
                 print(f"Warning: Child node {child_id} already exists?")

        # Rewire edges (Simplified)
        for u, _ in in_edges:
             if u != node_id:
                 for child_id in child_nodes:
                     if new_graph.has_node(u) and new_graph.has_node(child_id):
                         new_graph.add_edge(u, child_id)

        for _, v in out_edges:
             if v != node_id:
                 for child_id in child_nodes:
                      if new_graph.has_node(child_id) and new_graph.has_node(v):
                         new_graph.add_edge(child_id, v)

        # Remove the original node
        new_graph.remove_node(node_id)

        self.graph = new_graph

        # --- 3. Adjust Layout --- (Run spring layout initialized with current positions)
        if self.graph.number_of_nodes() > 1:
            try:
                print("Adjusting layout after explosion...")
                # Calculate k for optimal distance
                k = 0.8 / (self.graph.number_of_nodes()**0.5) # Heuristic for k
                self.node_positions = nx.spring_layout(self.graph, pos=new_positions, k=k, iterations=30, seed=42)
                print("Layout adjustment complete.")
            except Exception as e_layout:
                print(f"Error during layout adjustment: {e_layout}. Using previous positions.")
                self.node_positions = new_positions # Fallback to non-adjusted positions
        else:
            self.node_positions = new_positions # Use directly if only 0 or 1 node

        self.selected_node = None
        self.undo_button.configure(state="normal")

        print(f"Exploded {node_id}. New graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
        self.draw_graph() # Redraw with updated graph and adjusted positions

    def delete_node(self, node_id):
        """Deletes a node and its edges from the graph."""
        if not self.graph or not self.graph.has_node(node_id):
            print(f"Error: Node '{node_id}' not found for deletion.")
            return
        
        print(f"Deleting node: {node_id}")
        self._save_history() # Save state BEFORE deleting
        
        new_graph = self.graph.copy()
        new_graph.remove_node(node_id)
        self.graph = new_graph
        
        # Remove node position
        if self.node_positions:
            self.node_positions.pop(node_id, None) 
            
        # Deselect if the deleted node was selected
        if self.selected_node == node_id:
            self.selected_node = None
            
        # Ensure undo button is enabled (it should be after _save_history)
        self.undo_button.configure(state="normal") 
        
        print(f"Deleted {node_id}. New graph: {self.graph.number_of_nodes()} nodes, {self.graph.number_of_edges()} edges")
        self.draw_graph() # Redraw without the node

    def undo_last_action(self, event=None):
        """Reverts the last graph modification (explosion, deletion) and adjusts layout."""
        if not self.history:
            print("No history to undo.")
            return

        print("Undoing last action...")
        last_state = self.history.pop()
        self.graph = last_state['graph']
        restored_positions = last_state['positions'] 
        self.selected_node = None # Clear selection after undo

        # Adjust layout based on restored state
        if self.graph and restored_positions and self.graph.number_of_nodes() > 1:
            try:
                 print("Adjusting layout after undo...")
                 k = 0.8 / (self.graph.number_of_nodes()**0.5)
                 self.node_positions = nx.spring_layout(self.graph, pos=restored_positions, k=k, iterations=30, seed=42)
                 print("Layout adjustment complete.")
            except Exception as e_layout:
                 print(f"Error during layout adjustment: {e_layout}. Using restored positions directly.")
                 self.node_positions = restored_positions 
        else:
             self.node_positions = restored_positions 


        if not self.history:
             self.undo_button.configure(state="disabled")
        else: # Ensure it's enabled if history still exists
             self.undo_button.configure(state="normal")

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
                  self.undo_button.configure(state="normal")

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

    def load_dependencies(self):
        """Loads dependencies using tach, calculates layout, and displays the graph."""
        print("Loading dependencies...")
        # Reset graph-related state before loading
        self.graph = None
        self.node_positions = None
        self.selected_node = None
        self.history = []
        self.undo_button.configure(state="disabled")

        tach_data = self.run_tach()
        if tach_data:
            self.graph = self.build_graph_from_tach(tach_data) # Changed to assign to self.graph
            if self.graph:
                # Calculate initial layout here
                print("Calculating initial graph layout...")
                try:
                    if PYGRAPHVIZ_INSTALLED:
                        try:
                            self.node_positions = nx_agraph.graphviz_layout(self.graph, prog='dot')
                            print("Initial layout complete (using pygraphviz dot).")
                        except Exception as e_gv:
                            print(f"Initial pygraphviz failed: {e_gv}. Falling back.")
                            self.node_positions = nx.spring_layout(self.graph, seed=42)
                            print("Initial layout complete (spring fallback).")
                    else:
                        self.node_positions = nx.spring_layout(self.graph, seed=42)
                        print("Initial layout complete (spring - pygraphviz not installed).")
                except Exception as e_layout:
                     messagebox.showerror("Layout Error", f"Failed to calculate initial layout: {e_layout}")
                     self.graph = None # Invalidate graph if layout fails
                     return

                # Draw the graph with the calculated positions
                self.draw_graph()
                self._save_history() # Save initial state AFTER layout
            else:
                print("Failed to build graph from tach data.")
                # Clear any leftover plot
                self.ax.clear()
                self.ax.text(0.5, 0.5, "Failed to build graph", ha='center', va='center')
                self.canvas.draw_idle()
        else:
            print("Failed to get tach data.")
            # Clear any leftover plot
            self.ax.clear()
            self.ax.text(0.5, 0.5, "Failed to load data from tach", ha='center', va='center')
            self.canvas.draw_idle()

    # --- Add on_hover Method --- 
    def on_hover(self, event):
        """Handles mouse motion events to show tooltips over nodes."""
        if event.inaxes == self.ax and self.node_positions:
            node_under_cursor = self.find_node_at_pos(event.x, event.y)

            if node_under_cursor:
                if node_under_cursor != self.hovered_node:
                    self.hovered_node = node_under_cursor
                    tooltip_text = str(self.hovered_node)
                    self.tooltip_label.configure(text=tooltip_text)
                    
                    # Use event coordinates but invert Y relative to canvas height
                    tooltip_x = event.x + 15
                    try:
                        # Get canvas height for Y inversion
                        canvas_height = self.canvas_widget.winfo_height()
                        if canvas_height <= 1: # Check for invalid height initially
                             print("Warning: Canvas height not yet available for tooltip placement.")
                             tooltip_y = event.y + 10 # Fallback to previous simple placement
                        else:
                             tooltip_y = canvas_height - event.y + 10 # Invert Y, offset below cursor
                    except Exception as e:
                         print(f"Error getting canvas height: {e}")
                         tooltip_y = event.y + 10 # Fallback
                                        
                    self.tooltip_label.place(x=tooltip_x, y=tooltip_y)
                    # Update debug print if needed
                    print(f"Hover IN: {self.hovered_node} at canvas coords ({tooltip_x:.0f}, {tooltip_y:.0f}) using canvas_height={canvas_height if 'canvas_height' in locals() else 'N/A'}") # Debug
            else:
                if self.hovered_node is not None:
                    print(f"Hover OUT: {self.hovered_node}") # Debug
                    self.hovered_node = None
                    self.tooltip_label.place_forget()
        else:
            if self.hovered_node is not None:
                print(f"Hover OUTSIDE AXES: {self.hovered_node}") # Debug
                self.hovered_node = None
                self.tooltip_label.place_forget()

    # --- Rename Deflate Button Tooltip Handlers --- 
    def show_undo_tooltip(self, event=None):
        """Shows the tooltip for the undo button."""
        self.undo_tooltip_label.configure(text="Undo (CTRL+Z)") # Updated text
        # Position relative to the undo button
        button_x = self.undo_button.winfo_x()
        button_y = self.undo_button.winfo_y()
        button_height = self.undo_button.winfo_height()
        
        tooltip_x = button_x 
        tooltip_y = button_y + button_height + 5 
        
        self.undo_tooltip_label.place(x=tooltip_x, y=tooltip_y)
        print("Show undo tooltip") # Debug

    def hide_undo_tooltip(self, event=None):
        """Hides the tooltip for the undo button."""
        self.undo_tooltip_label.place_forget()
        print("Hide undo tooltip") # Debug


# --- Entry Point ---
def run_gui():
    """Initializes and runs the main Tkinter application loop."""
    print("--- run_gui() started ---")
    try:
        # Ensure matplotlib is using the proper backend for tkinter
        import matplotlib
        matplotlib.use('TkAgg')  # Force TkAgg backend for better event handling
        
        # Set appearance mode and color theme
        try:
            ctk.set_appearance_mode("System") # Default to system theme (light or dark)
        except Exception as e:
            print(f"Warning: Could not set appearance mode 'System'. Falling back to 'Light'. Error: {e}", file=sys.stderr)
            ctk.set_appearance_mode("Light") # Fallback

        try:
            ctk.set_default_color_theme("blue") # Default theme
        except Exception as e:
            print(f"Warning: Could not set color theme 'blue'. Using default. Error: {e}", file=sys.stderr)
            # No explicit fallback needed, CustomTkinter handles it

        print("--- Appearance set ---")
        app = DependencyVisualizerApp()
        print("--- DependencyVisualizerApp initialized ---")

        # --- Bind CTRL+Z to Undo ---
        def handle_ctrl_z(event):
            app.undo_last_action() # Call the app's undo method

        app.bind_all("<Control-z>", handle_ctrl_z) # Bind globally

        app.mainloop()
    except Exception as e:
        print(f"--- !!! An error occurred during GUI startup: {e} !!! ---", file=sys.stderr)
        import traceback
        traceback.print_exc()
        try:
            messagebox.showerror("Startup Error", f"An error occurred during application startup:\n\n{e}")
        except Exception as dialog_error:
            print(f"--- Could not even show error dialog: {dialog_error} ---", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    run_gui() # Allows running directly via python src/dependency_visualizer/main.py 