# Top-level data processor that uses functionality from deeper modules

import pandas as pd
from .deep_module.math_utils import calculate_statistics
from .deep_module.deeper.deepest.science_module import analyze_data, plot_data

class DataProcessor:
    """A class that processes data using various scientific libraries."""
    
    def __init__(self, data_source):
        """Initialize with data source path or object."""
        self.data_source = data_source
        self.data = None
        self.results = {}
    
    def load_data(self):
        """Load data from the source."""
        if isinstance(self.data_source, str):
            # Assume it's a path to a CSV file
            self.data = pd.read_csv(self.data_source)
        else:
            # Assume it's already a data object
            self.data = pd.DataFrame(self.data_source)
        
        return self.data
    
    def process(self):
        """Process the data using various scientific functions."""
        if self.data is None:
            self.load_data()
        
        # Extract a numeric column or convert data to numeric array
        numeric_data = self.data.select_dtypes(include=['number']).iloc[:, 0].values
        
        # Use functions from deeper modules
        self.results['statistics'] = calculate_statistics(numeric_data)
        self.results['analysis'] = analyze_data(numeric_data)
        
        return self.results
    
    def visualize(self):
        """Create visualizations of the data."""
        if self.data is None:
            self.load_data()
        
        numeric_data = self.data.select_dtypes(include=['number']).iloc[:, 0].values
        return plot_data(numeric_data) 