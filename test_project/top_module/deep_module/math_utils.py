# Math utilities module at an intermediate nesting level

import numpy as np
from scipy import stats
import tensorflow as tf  # Another external dependency

def calculate_statistics(data_list):
    """Calculate various statistics using numpy and scipy."""
    data = np.array(data_list)
    
    return {
        'mean': np.mean(data),
        'median': np.median(data),
        'std_dev': np.std(data),
        'variance': np.var(data),
        'skewness': stats.skew(data),
        'kurtosis': stats.kurtosis(data)
    }

def create_neural_network():
    """Create a simple neural network using TensorFlow."""
    model = tf.keras.Sequential([
        tf.keras.layers.Dense(128, activation='relu'),
        tf.keras.layers.Dense(64, activation='relu'),
        tf.keras.layers.Dense(10, activation='softmax')
    ])
    
    return model