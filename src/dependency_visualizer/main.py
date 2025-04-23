import os
import re
import sys
import json
import math
import time
import textwrap # For potential wrapping if needed
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox
import matplotlib
matplotlib.use('TkAgg')  # This must come before pyplot import
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import networkx as nx
import customtkinter as ctk
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

# Check for scipy availability (needed for spring_layout)
SCIPY_INSTALLED = False
try:
    import scipy
    SCIPY_INSTALLED = True
except ImportError:
    print("\n[ERROR] scipy not found but it is a required dependency.")
    print("        Please ensure the package was installed correctly: pip install dependency-visualizer\n")
    print("        The application will use fallback layout algorithms but optimal visualization requires scipy.\n")

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
        self.panning = not self.panning  # Toggle panning state
        if self.panning:
            self.view_limits = (self.app.ax.get_xlim(), self.app.ax.get_ylim())
        super().pan(*args)

    def zoom(self, *args):
        """Override zoom action start/toggle."""
        self.zooming = not self.zooming  # Toggle zooming state
        if self.zooming:
            self.view_limits = (self.app.ax.get_xlim(), self.app.ax.get_ylim())
        super().zoom(*args)

    def release_pan(self, event):
        """Override pan action release (mouse button up)."""
        current_xlim = self.app.ax.get_xlim()
        current_ylim = self.app.ax.get_ylim()
        
        super().release_pan(event)
        
        if not self.panning:
            current_positions = self.app.node_positions.copy() if self.app.node_positions else None
            self.app.draw_graph(highlight_node=self.app.selected_node, preserve_view=True)
            
            if current_positions:
                self.app.node_positions = current_positions
            
            self.app.ax.set_xlim(current_xlim)
            self.app.ax.set_ylim(current_ylim)
            self.canvas.draw()  # Force canvas update with restored limits

    def release_zoom(self, event):
        """Override zoom action release (mouse button up after drawing zoom box)."""
        current_xlim = self.app.ax.get_xlim()
        current_ylim = self.app.ax.get_ylim()
        
        super().release_zoom(event)
        
        new_xlim = self.app.ax.get_xlim()
        new_ylim = self.app.ax.get_ylim()
        
        current_positions = self.app.node_positions.copy() if self.app.node_positions else None
        self.app.draw_graph(highlight_node=self.app.selected_node, preserve_view=True)
        
        if current_positions:
            self.app.node_positions = current_positions
            
        self.app.ax.set_xlim(new_xlim)
        self.app.ax.set_ylim(new_ylim)
        self.canvas.draw()  # Force canvas update with restored limits

    # Modify scroll_event override for mouse wheel zoom
    def scroll_event(self, event):
        """Override scroll event to handle mouse wheel zoom with preserved view."""
        current_xlim = self.app.ax.get_xlim()
        current_ylim = self.app.ax.get_ylim()
        
        super().scroll_event(event)
        
        new_xlim = self.app.ax.get_xlim()
        new_ylim = self.app.ax.get_ylim()
        
        self.canvas.get_tk_widget().after(
            50, 
            lambda: self._redraw_after_scroll(new_xlim, new_ylim, current_positions=self.app.node_positions.copy())
        ) 

    # Update helper method for delayed redraw
    def _redraw_after_scroll(self, xlim, ylim, current_positions=None):
        """Helper method to redraw the graph with highlights while preserving zoom state."""
        self.app.draw_graph(highlight_node=self.app.selected_node, preserve_view=True)
        
        if current_positions:
            self.app.node_positions = current_positions
        
        self.ax.set_xlim(xlim)
        self.ax.set_ylim(ylim)
        
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

        # --- Bind window close event --- 
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

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
        # print(f"Writing/Updating {tach_config_path} with current exclude patterns.")
        
        # Initialize source_roots list
        source_roots = ["."] # Always include the project root

        # Check if src directory exists and add it if it does
        src_dir_path = os.path.join(self.project_root, "src")
        if os.path.isdir(src_dir_path):
             source_roots.append("src")

        config = {
            "modules": [], # Start with empty modules list; we'll define source roots
            "source_roots": source_roots, # Use the determined source roots
            "force_package_roots": ["."] # Treat project root as package regardless of __init__.py
        }

        # Add excludes if any exist
        if user_exclude_patterns: # Use the local variable read from the UI
             config["exclude"] = user_exclude_patterns # Use the local variable

        # Generate config content using UI exclude patterns
        config_content = f"""# Auto-generated/Updated by Dependency Visualizer

source_roots = ["{source_roots[0]}"]

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
        top_level_packages = set()  # Store top-level packages only

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

        def get_top_level_package(package_name):
            """Extract the top-level package name from a dotted package path."""
            if package_name.startswith("ext:"):
                return package_name  # External dependencies remain as-is
            
            # For internal packages, get the first component
            parts = package_name.split('.')
            if parts:
                return parts[0]
            return package_name

        all_packages = set()
        # First pass: collect all packages and their dependencies
        detailed_package_dependencies = {}  # Full dependency details before collapsing
        
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
            if source_pkg not in detailed_package_dependencies:
                detailed_package_dependencies[source_pkg] = set()

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
                        detailed_package_dependencies[source_pkg].add(target_pkg)
                else:
                     print(f"Warning: Could not determine package for target file '{target_file}'")

        # Second pass: collapse sub-packages to top-level packages
        for pkg in all_packages:
            top_pkg = get_top_level_package(pkg)
            top_level_packages.add(top_pkg)
            
            # Add to package_dependencies if not already there
            if top_pkg not in package_dependencies:
                package_dependencies[top_pkg] = set()
                
        # Aggregate dependencies at top level
        for source_pkg, targets in detailed_package_dependencies.items():
            top_source = get_top_level_package(source_pkg)
            
            for target_pkg in targets:
                top_target = get_top_level_package(target_pkg)
                
                # Only add dependency if top-level packages are different
                if top_source != top_target:
                    package_dependencies[top_source].add(top_target)
        
        print(f"Collapsed to {len(top_level_packages)} top-level packages: {sorted(list(top_level_packages))}")

        # Add nodes for all top-level packages
        for pkg_name in top_level_packages:
            # Add node attributes for visualization based on package type
            if pkg_name.startswith("ext:"):
                # External package - use different attributes
                G.add_node(pkg_name, is_external=True)
            else:
                # Internal project package
                G.add_node(pkg_name, is_external=False)
                
        print(f"Added {len(top_level_packages)} package nodes")
        external_top_pkgs = [p for p in top_level_packages if p.startswith("ext:")]
        print(f"External packages: {sorted(external_top_pkgs)}")

        # Add edges based on the aggregated top-level package dependencies
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
                    # Try pygraphviz first if installed
                    if PYGRAPHVIZ_INSTALLED:
                        self.node_positions = nx_agraph.graphviz_layout(self.graph, prog='dot')
                    else:
                        # Fall back to spring_layout with scipy
                        if SCIPY_INSTALLED:
                            # Safely try to use spring_layout which depends on scipy
                            self.node_positions = nx.spring_layout(self.graph, seed=42)
                        else:
                            # Simple fallback if scipy is not available - use circular layout
                            print("Using circular_layout as fallback due to missing scipy dependency")
                            self.node_positions = nx.circular_layout(self.graph)
                        
                except Exception as e: 
                    print(f"Failed to calculate initial layout: {e}")
                    try:
                        # Last resort - use shell layout or circular layout which don't need scipy
                        print("Attempting circular_layout as last resort")
                        self.node_positions = nx.circular_layout(self.graph)
                    except Exception as e2:
                        messagebox.showerror("Layout Error", f"Failed to calculate any layout: {e2}")
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
            return
            
        # Skip normal click processing if we're in zoom or pan mode
        if hasattr(self.toolbar, 'mode') and self.toolbar.mode in ('zoom rect', 'pan/zoom'):
            return

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
            self._last_click_time = 0 # Reset time
            print("DEBUG: Double-click detected (manual detection)") # Re-enable print
        else:
            self._last_click_time = current_time
            self._last_click_event = event

        # --- Right-Click Action (Button 3) ---
        if event.button == 3: # Restore original 'if'
            # print(f"Right-click detected. Node: {clicked_node}")
            if clicked_node:
                self.delete_node(clicked_node)
            return

        # --- Double-Click Action (Button 1) ---
        elif event.button == 1 and is_double_click:
            print(f"DEBUG: Double-click detected on node: {clicked_node}") # Re-enable print
            if clicked_node:
                self.handle_double_click(event)
            return

        # --- Single-Click Action (Button 1) ---
        elif event.button == 1 and not is_double_click:
             # print(f"Left-click processing. Node: {clicked_node}")
            def delayed_single_click_action():
                if time.time() - self._last_click_time > self._double_click_threshold:
                    if clicked_node:
                        if self.selected_node == clicked_node:
                            self.selected_node = None
                        else:
                            self.selected_node = clicked_node
                    else:
                        if self.selected_node:
                            self.selected_node = None
                    
                    current_xlim = self.ax.get_xlim()
                    current_ylim = self.ax.get_ylim()
                    
                    self.draw_graph(highlight_node=self.selected_node, preserve_view=True)
                    
                    self.ax.set_xlim(current_xlim)
                    self.ax.set_ylim(current_ylim)
                    self.canvas.draw()
            
            self.after(int(self._double_click_threshold * 1000), delayed_single_click_action)

    def handle_double_click(self, event):
        """Handles double-click events for node explosion."""
        print(f"DEBUG: Handling double click...") # Re-enable print
        node_to_explode = self.find_node_at_pos(event.x, event.y)
        if node_to_explode:
            print(f"DEBUG: Attempting to explode node: {node_to_explode}") # Re-enable print
            self.explode_module(node_to_explode)
        else:
            print(f"DEBUG: No node found at double-click position.") # Add else print

    def explode_module(self, node_id):
        """Expands a package/directory node to show its immediate children,
        rewiring edges based on detailed file-level dependencies from tach_data.
        """
        # --- Prerequisites ---
        if not hasattr(self, 'tach_project_root') or not self.tach_project_root:
            messagebox.showerror("Error", "Tach project root not determined. Cannot explode.")
            return
        if not self.graph or not self.graph.has_node(node_id):
            messagebox.showerror("Error", f"Node '{node_id}' not found in graph.")
            return
        if not hasattr(self, 'tach_data') or not self.tach_data:
             messagebox.showerror("Error", "Tach data not available. Cannot accurately explode node.")
             return # Need tach_data for accurate rewiring

        print(f"Exploding package/directory: {node_id}")

        # --- 1. Find immediate children (submodules/subpackages/scripts) ---
        # Use '.' for the root node if node_id is '.'
        relative_node_path = node_id if node_id != '.' else ''
        potential_dir = os.path.join(self.tach_project_root, relative_node_path.replace('.', os.sep))

        # If node_id is 'ext:something', we cannot explode further
        if node_id.startswith("ext:"):
            messagebox.showinfo("Cannot Explode", f"External package node '{node_id}' cannot be exploded.")
            return

        # Check if it's a directory or represents one
        is_directory_like = False
        if os.path.isdir(potential_dir):
             is_directory_like = True
        elif node_id == '.': # Root is always directory-like
             is_directory_like = True
        # Add more checks if node names might represent files directly in some cases

        if not is_directory_like:
             # This node might represent a single module/script already
             print(f"Node '{node_id}' does not appear to be a directory: {potential_dir}. Assuming it's already exploded.")
             messagebox.showinfo("Cannot Explode", f"Node '{node_id}' does not seem to be a package or directory that can be exploded further.")
             return

        children_details = {} # Store { child_node_id: child_file_path }
        try:
            for item in os.listdir(potential_dir):
                item_path_abs = os.path.join(potential_dir, item)
                # item_path_rel = os.path.relpath(item_path_abs, self.tach_project_root).replace('\\\\', '/') # Old way

                # --- Use pathlib for robust relative path and name derivation ---
                try:
                    p_rel = Path(item_path_abs).relative_to(self.tach_project_root)
                    normalized_rel_path = p_rel.as_posix() # Path with forward slashes
                except ValueError as e:
                    print(f"  Warning: Could not get relative path for {item_path_abs}: {e}")
                    continue # Skip this item

                child_id = None
                representative_file_path = None
                # Check if it's a directory containing __init__.py (sub-package)
                if os.path.isdir(item_path_abs) and os.path.exists(os.path.join(item_path_abs, '__init__.py')):
                    # Node name is the dot-separated directory path
                    child_id = normalized_rel_path.replace('/', '.') # e.g., 'pkg_b.sub_b'
                    # Store the path to the __init__.py as the representative file
                    representative_file_path = (p_rel / '__init__.py').as_posix()

                # Check if it's a .py file (sub-module/script)
                elif os.path.isfile(item_path_abs) and item.endswith('.py') and item != '__init__.py':
                    # Node name is dot-separated path excluding extension
                    base_path = os.path.splitext(normalized_rel_path)[0] # e.g., 'pkg_b/sub_b/logic_b'
                    child_id = base_path.replace('/', '.') # e.g., 'pkg_b.sub_b.logic_b'
                    representative_file_path = normalized_rel_path # Store the .py file path

                # --- Store child details if found ---
                if child_id and representative_file_path:
                     children_details[child_id] = representative_file_path

        except OSError as e:
             messagebox.showerror("Error", f"Error accessing sub-items for '{node_id}': {e}")
             return

        if not children_details:
            print(f"No children (sub-packages or modules/scripts) found for {node_id}")
            messagebox.showinfo("No Children", f"No sub-packages or modules/scripts found within '{node_id}' to explode.")
            return

        print(f"Found {len(children_details)} direct children for {node_id}: {list(children_details.keys())}")

        # --- 2. Modify Graph ---
        self._save_history() # Save state *before* modification

        new_graph = self.graph.copy()
        new_positions = self.node_positions.copy() if self.node_positions else {}

        # Store original node info & remove original node
        original_pos = new_positions.pop(node_id, None)
        if new_graph.has_node(node_id):
             new_graph.remove_node(node_id)
        else:
             print(f"Warning: Node {node_id} to explode was already removed?")


        # Add new nodes for children & estimate initial positions
        child_nodes = list(children_details.keys())
        for child_id in child_nodes:
             if not new_graph.has_node(child_id):
                 new_graph.add_node(child_id, is_external=False)
                 if original_pos is not None:
                      # Simple offset logic for initial placement
                      offset_x = (hash(child_id) % 200 - 100) / 1000.0
                      offset_y = (hash(child_id) % 100 - 50) / 1000.0
                      new_positions[child_id] = (original_pos[0] + offset_x, original_pos[1] + offset_y)
                 else:
                      new_positions[child_id] = (0.5, 0.5) # Fallback position
             else:
                 print(f"Warning: Child node {child_id} already exists in graph?")

        # --- DEBUG: Print graph nodes before edge rebuild ---
        print(f"DEBUG: Nodes in graph before edge rebuild: {sorted(list(new_graph.nodes()))}")
        # --- END DEBUG ---

        # --- 3. Rebuild Edges based on tach_data ---
        print("Rebuilding edges based on tach_data...")
        added_edges = set()
        for source_filepath, target_filepaths in self.tach_data.items():
            # Map source filepath to a node in the *new* graph state
            source_node = self._map_filepath_to_graph_node(source_filepath, new_graph)
            # --- DEBUG START ---
            # print(f"Processing source: {source_filepath} -> Mapped Node: {source_node}")
            # --- DEBUG END ---

            if source_node:
                for target_filepath in target_filepaths:
                    # Map target filepath to a node in the *new* graph state
                    target_node = self._map_filepath_to_graph_node(target_filepath, new_graph)
                    # --- DEBUG START ---
                    mapped_edge_info = f"  Target: {target_filepath} -> Mapped Node: {target_node}"
                    # --- DEBUG END ---

                    if target_node and source_node != target_node:
                        # Add edge if both nodes exist in the new graph and are different
                        edge = (source_node, target_node)
                        if edge not in added_edges:
                             # --- DEBUG START ---
                             print(f"DEBUG: Adding Edge | {mapped_edge_info} | Result: {source_node} -> {target_node}")
                             # --- DEBUG END ---
                             new_graph.add_edge(source_node, target_node)
                             added_edges.add(edge)
                             # print(f"  Added edge: {source_node} -> {target_node} (from {source_filepath} -> {target_filepath})")
                    # --- DEBUG START ---
                    # else:
                         # Optional: Print why edge wasn't added
                         # reason = ""
                         # if not target_node: reason = "Target node not found in graph."
                         # elif source_node == target_node: reason = "Source and target map to same node."
                         # print(f"DEBUG: Skipping Edge | {mapped_edge_info} | Reason: {reason}")
                    # --- DEBUG END ---


        self.graph = new_graph

        # --- 4. Adjust Layout ---
        # (Layout logic remains similar, using new_positions as initial state)
        if self.graph.number_of_nodes() > 1:
            try:
                print("Adjusting layout after explosion...")
                current_positions_for_layout = {n: p for n, p in new_positions.items() if n in self.graph}

                if PYGRAPHVIZ_INSTALLED:
                     # If using graphviz, maybe just recalculate dot?
                     # Or does spring layout work better after explosion? Let's stick to spring for consistency post-explosion.
                     print("Using spring_layout for post-explosion adjustment (PyGraphviz available but spring preferred here)")
                     if SCIPY_INSTALLED:
                         k = 0.8 / (self.graph.number_of_nodes()**0.5) # Heuristic for k
                         self.node_positions = nx.spring_layout(self.graph, pos=current_positions_for_layout, k=k, iterations=30, seed=42)
                     else:
                         print("Falling back to circular layout post-explosion (scipy not available)")
                         self.node_positions = nx.circular_layout(self.graph) # Less ideal adjustment

                elif SCIPY_INSTALLED:
                    k = 0.8 / (self.graph.number_of_nodes()**0.5) # Heuristic for k
                    self.node_positions = nx.spring_layout(self.graph, pos=current_positions_for_layout, k=k, iterations=30, seed=42)
                else:
                    print("Using circular_layout for post-explosion adjustment (scipy not available)")
                    # Simple circular layout if no better option
                    self.node_positions = nx.circular_layout(self.graph)

                print("Layout adjustment complete.")
            except Exception as e_layout:
                print(f"Error during layout adjustment: {e_layout}. Using estimated positions.")
                # Fallback to the initially estimated positions if layout fails
                self.node_positions = {n: p for n, p in new_positions.items() if n in self.graph}
        else:
            self.node_positions = {n: p for n, p in new_positions.items() if n in self.graph} # Use directly if only 0 or 1 node


        # --- 5. Finalize and Redraw ---
        self.selected_node = None # Clear selection after explosion
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
                # Use scipy if available, otherwise use alternatives
                if SCIPY_INSTALLED:
                    k = 0.8 / (self.graph.number_of_nodes()**0.5)
                    self.node_positions = nx.spring_layout(self.graph, pos=restored_positions, k=k, iterations=30, seed=42)
                else:
                    # Just use the restored positions directly
                    print("Using restored positions directly (scipy not available)")
                    self.node_positions = restored_positions
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
             print(f"DEBUG: Click near node: {closest_node}") # Re-enable print
             return closest_node
        else:
             # print(f"Click not close enough to any node (min_dist_sq={min_dist_sq:.2f})")
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
        self.tach_data = None # Explicitly clear previous data

        tach_data = self.run_tach()
        if tach_data:
            self.tach_data = tach_data # Assign the data to the instance variable
            self.graph = self.build_graph_from_tach(self.tach_data) # Use the instance variable
            if self.graph:
                # Calculate initial layout here
                print("Calculating initial graph layout...")
                try:
                    # First try: Use pygraphviz if available
                    if PYGRAPHVIZ_INSTALLED:
                        try:
                            self.node_positions = nx_agraph.graphviz_layout(self.graph, prog='dot')
                            print("Initial layout complete (using pygraphviz dot).")
                        except Exception as e_gv:
                            print(f"Initial pygraphviz failed: {e_gv}. Falling back to spring_layout.")
                            if SCIPY_INSTALLED:
                                # Second try: Use spring_layout with networkx (requires scipy)
                                self.node_positions = nx.spring_layout(self.graph, seed=42)
                                print("Initial layout complete (spring_layout fallback).")
                            else:
                                # Use circular layout if scipy not available
                                print("Using circular_layout (scipy not available)")
                                self.node_positions = nx.circular_layout(self.graph)
                                print("Initial layout complete (circular_layout fallback).")
                    else:
                        if SCIPY_INSTALLED:
                            # For no pygraphviz: Try spring_layout first (requires scipy)
                            self.node_positions = nx.spring_layout(self.graph, seed=42)
                            print("Initial layout complete (spring_layout - pygraphviz not installed).")
                        else:
                            # Use circular layout if scipy not available
                            print("Using circular_layout (scipy not available)")
                            self.node_positions = nx.circular_layout(self.graph)
                            print("Initial layout complete (circular_layout fallback).")
                except Exception as e_layout:
                    print(f"All layout algorithms failed: {e_layout}. Using manual layout.")
                    # Final fallback: manual layout
                    try:
                        self.node_positions = self._generate_manual_layout()
                        print("Using manually generated layout as last resort.")
                    except Exception as e_manual:
                        messagebox.showerror("Layout Error", 
                            f"Failed to calculate any layout: {e_manual}\n\n"
                            "This might be due to missing dependencies or an extremely large graph.")
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
            
    def _generate_manual_layout(self):
        """Generate a simple manual layout as a last resort when all algorithms fail."""
        if not self.graph:
            return {}
            
        positions = {}
        nodes = list(self.graph.nodes())
        
        # Generate a simple circular layout manually
        num_nodes = len(nodes)
        if num_nodes == 0:
            return positions
            
        radius = 1.0
        center_x, center_y = 0.5, 0.5
        
        for i, node in enumerate(nodes):
            # Calculate position on a circle
            angle = 2.0 * math.pi * i / num_nodes
            x = center_x + radius * math.cos(angle)
            y = center_y + radius * math.sin(angle)
            positions[node] = (x, y)
            
        return positions

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
                        canvas_height = self.canvas_widget.winfo_height()
                        if canvas_height <= 1:
                             tooltip_y = event.y + 10
                        else:
                             tooltip_y = canvas_height - event.y + 10
                    except Exception as e:
                         tooltip_y = event.y + 10
                    self.tooltip_label.place(x=tooltip_x, y=tooltip_y)
            else:
                if self.hovered_node is not None:
                    self.hovered_node = None
                    self.tooltip_label.place_forget()
        else:
            if self.hovered_node is not None:
                self.hovered_node = None
                self.tooltip_label.place_forget()

    # --- Rename Deflate Button Tooltip Handlers --- 
    def show_undo_tooltip(self, event=None):
        """Shows the tooltip for the undo button."""
        self.undo_tooltip_label.configure(text="Undo (CTRL+Z)")
        button_x = self.undo_button.winfo_x()
        button_y = self.undo_button.winfo_y()
        button_height = self.undo_button.winfo_height()
        
        tooltip_x = button_x 
        tooltip_y = button_y + button_height + 5 
        
        self.undo_tooltip_label.place(x=tooltip_x, y=tooltip_y)

    def hide_undo_tooltip(self, event=None):
        """Hides the tooltip for the undo button."""
        self.undo_tooltip_label.place_forget()

    # --- Add Helper Function for Filepath to Node Mapping ---
    def _map_filepath_to_graph_node(self, filepath, graph):
        """Maps a file path (relative to project root) to its corresponding node
           in the *current* graph state.

        Args:
            filepath: The relative file path (e.g., 'pkg_a/module_a.py').
            graph: The networkx graph instance to check against.

        Returns:
            The name of the node in the graph representing this filepath,
            or None if no corresponding node exists in the current graph state.
        """
        print(f"_map_filepath_to_graph_node: Trying to map '{filepath}'")
        if not filepath or not graph:
            return None

        # --- Robust Normalization and Dot Conversion ---
        try:
            # 1. Normalize separators to POSIX style first
            normalized_path = Path(filepath).as_posix()

            # 2. Handle __init__.py separately to get parent dir path
            if normalized_path.endswith('/__init__.py'):
                # Get parent dir, could be empty for root __init__.py
                path_base = os.path.dirname(normalized_path)
                # Convert slashes to dots, handle root case
                potential_node = path_base.replace('/', '.') if path_base else '.'
            else:
                # For other files, remove .py extension if present
                path_base = os.path.splitext(normalized_path)[0]
                # Convert slashes to dots
                potential_node = path_base.replace('/', '.')

        except TypeError as e:
             print(f"  ERROR: Could not process filepath '{filepath}' with Pathlib: {e}")
             return None

        # --- External Check (moved after potential_node derivation) ---
        if not os.path.exists(os.path.join(self.tach_project_root, filepath)):
            parts = potential_node.split('.') # Use dot-separated name now
            if parts and parts[0]:
                 external_node_candidate = f"ext:{parts[0]}"
                 print(f"  Potential Node (External Check on '{potential_node}'): {external_node_candidate}")
                 if graph.has_node(external_node_candidate):
                      print(f"  FOUND (External): {external_node_candidate}")
                      return external_node_candidate
                 print(f"  NOT FOUND (External): {external_node_candidate}")
                 return None
            else:
                 print(f"  Cannot determine external package from: {potential_node}")
                 return None

        # --- Internal Node Check ---
        print(f"  Potential Node (Internal): {potential_node}")

        # 2. Check if the exact potential node name exists in the graph
        if graph.has_node(potential_node):
            print(f"  FOUND (Exact Internal): {potential_node}")
            return potential_node

        # 3. If exact match not found, try finding the parent package/directory node
        parts = potential_node.split('.')
        for i in range(len(parts) - 1, 0, -1):
             parent_node_name = '.'.join(parts[:i])
             # --- DEBUG START ---
             print(f"    Checking parent: {parent_node_name}") # Ensure this is uncommented
             # --- DEBUG END ---
             if graph.has_node(parent_node_name):
                 # --- DEBUG START ---
                 print(f"    FOUND (Parent Match): {parent_node_name}") # Ensure this is uncommented
                 # --- DEBUG END ---
                 return parent_node_name

        # 4. Check if it belongs to the root node (if '.' node exists)
        # --- DEBUG START ---
        print(f"    Checking for root node '.' mapping...") # Ensure this is uncommented
        # --- DEBUG END ---
        if graph.has_node('.'):
            if '/' not in normalized_path and '\\\\' not in normalized_path:
                   # --- DEBUG START ---
                   print(f"    FOUND (Root Match): '.'") # Ensure this is uncommented
                   # --- DEBUG END ---
                   return '.'

        # --- DEBUG START ---
        print(f"  Mapping FAILED for '{filepath}'. Returning None.") # Ensure this is uncommented
        # --- DEBUG END ---
        return None

    # --- Add the on_closing method ---
    def on_closing(self):
        """Handles the event when the window is closed by the user."""
        print("Window close requested. Cleaning up and exiting...")
        try:
            # Ensure matplotlib figure is closed if exists
            if hasattr(self, 'fig') and self.fig:
                 plt.close(self.fig)
            # Quit the Tkinter main loop
            self.quit()
            # Destroy the main window and widgets
            self.destroy()
            print("Application closed successfully.")
        except Exception as e:
            print(f"Error during closing sequence: {e}")
            # Optionally force exit if standard cleanup fails
            # import sys
            # sys.exit(1)


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