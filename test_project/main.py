# Main test file for dependency-visualizer demonstration
# This file shows imports at various levels of nesting

import numpy as np
import pandas as pd
from top_module.data_processor import DataProcessor
from top_module.deep_module.math_utils import calculate_statistics
from top_module.deep_module.deeper.deepest.science_module import analyze_data, plot_data

def main():
    """Main function to demonstrate the package structure and dependencies."""
    # Create some sample data
    data = np.random.randn(100)
    
    # Process directly with the nested module functions
    print("Direct function calls:")
    stats = calculate_statistics(data)
    print(f"Statistics: Mean={stats['mean']:.2f}, StdDev={stats['std_dev']:.2f}")
    
    analysis = analyze_data(data)
    print(f"Analysis: Mean={analysis['mean']:.2f}, StdDev={analysis['std']:.2f}")
    
    # Process with the high-level processor
    print("\nProcessing with DataProcessor:")
    processor = DataProcessor(data)
    results = processor.process()
    
    print("Processing complete!")
    
    # The dependencies that should be visible in the visualization:
    # main.py → numpy, pandas
    # main.py → top_module.data_processor
    # main.py → top_module.deep_module.math_utils
    # main.py → top_module.deep_module.deeper.deepest.science_module
    # 
    # top_module.data_processor → pandas
    # top_module.data_processor → top_module.deep_module.math_utils
    # top_module.data_processor → top_module.deep_module.deeper.deepest.science_module
    # 
    # top_module.deep_module.math_utils → numpy, scipy, tensorflow
    #
    # top_module.deep_module.deeper.deepest.science_module → numpy, scipy, matplotlib, pandas

if __name__ == "__main__":
    main() 