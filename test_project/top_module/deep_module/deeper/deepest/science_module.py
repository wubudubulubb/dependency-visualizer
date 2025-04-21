# This module tests external dependency handling

import numpy as np
import scipy
import scipy.optimize
import matplotlib.pyplot as plt
from pandas import DataFrame

def analyze_data(data):
    """
    Analyze data using scientific libraries.
    Test function that uses multiple external dependencies.
    """
    # Convert to numpy array
    arr = np.array(data)
    
    # Use scipy for optimization
    result = scipy.optimize.minimize(lambda x: np.sum((x - arr)**2), np.zeros_like(arr))
    
    # Create a DataFrame for data manipulation
    df = DataFrame({'original': arr, 'optimized': result.x})
    
    return {
        'mean': np.mean(arr),
        'std': np.std(arr),
        'optimized': result.x,
        'dataframe': df
    }

def plot_data(data):
    """Plot the data using matplotlib."""
    plt.figure(figsize=(10, 6))
    plt.plot(data, 'o-', label='Data')
    plt.title('Scientific Data Visualization')
    plt.xlabel('Index')
    plt.ylabel('Value')
    plt.legend()
    plt.grid(True)
    return plt.gcf() 