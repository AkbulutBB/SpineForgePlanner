#!/usr/bin/env python3
"""
ICC Analysis Script for Surgimap vs SpineForge Planner Comparison
===============================================================

This script performs Intraclass Correlation Coefficient (ICC) analysis and time comparison
between Surgimap and SpineForge Planner measurement methods for spine surgical planning.

For single rater comparing two methods: ICC(3,1) - Two-way mixed model, consistency agreement
This is appropriate for comparing two measurement techniques by the same evaluator.

UPDATES:
- Handles HH:MM:SS time format conversion
- Uses absolute values for angle measurements to eliminate direction dependency

Author: SpineForge Development Team
Version: 0.4
Compatible with: SpineForge Planner v0.4
"""

import pandas as pd
import numpy as np
import scipy.stats as stats
from scipy import stats as scipy_stats
import matplotlib.pyplot as plt
import seaborn as sns
from statsmodels.stats.contingency_tables import mcnemar
import warnings
warnings.filterwarnings('ignore')

class ICCAnalyzer:
    """Class for performing ICC analysis between two measurement methods"""
    
    def __init__(self, data_file=None):
        """
        Initialize the ICC analyzer
        
        Parameters:
        -----------
        data_file : str, optional
            Path to CSV file containing measurement data
        """
        self.data = None
        self.results = {}
        
        if data_file:
            self.load_data(data_file)
    
    def load_data(self, file_path):
        """
        Load measurement data from CSV file
        
        Expected format:
        - Row-based data with measurements in first column
        - Rows starting with 'SP - ' for SpineForge measurements
        - Rows starting with 'SM - ' for Surgimap measurements
        - Time data in HH:MM:SS format
        """
        try:
            self.data = pd.read_csv(file_path)
            print(f"✓ Data loaded successfully: {self.data.shape[0]} cases, {self.data.shape[1]} variables")
            
            # Identify measurement pairs
            self.measurement_pairs = self._identify_measurement_pairs()
            print(f"✓ Found {len(self.measurement_pairs)} measurement pairs")
            
            return True
        except Exception as e:
            print(f"✗ Error loading data: {e}")
            return False
    
    def _identify_measurement_pairs(self):
        """Identify matching measurement pairs between SM and SP methods"""
        # In this data format, measurements are in rows, cases are in columns
        # First column contains measurement names
        measurement_names = self.data.iloc[:, 0].values
        
        pairs = []
        sp_measurements = {}
        sm_measurements = {}
        
        # Identify SP and SM measurements
        for idx, name in enumerate(measurement_names):
            if isinstance(name, str):
                if name.startswith('SP - '):
                    measure_type = name.replace('SP - ', '')
                    sp_measurements[measure_type] = idx
                elif name.startswith('SM - '):
                    measure_type = name.replace('SM - ', '')
                    sm_measurements[measure_type] = idx
        
        # Find matching pairs
        for measure_type in sp_measurements:
            if measure_type in sm_measurements:
                pairs.append((measure_type, sm_measurements[measure_type], sp_measurements[measure_type]))
        
        return pairs
    
    def convert_time_to_seconds(self, time_str):
        """Convert time string in HH:MM:SS format to seconds"""
        if pd.isna(time_str) or time_str == '':
            return np.nan
        
        try:
            # Handle different time formats
            time_str = str(time_str).strip()
            
            # If it's already a number, return as is
            try:
                return float(time_str)
            except ValueError:
                pass
            
            # Parse HH:MM:SS format
            if ':' in time_str:
                parts = time_str.split(':')
                if len(parts) == 3:  # HH:MM:SS
                    hours = int(parts[0])
                    minutes = int(parts[1])
                    seconds = int(parts[2])
                    return hours * 3600 + minutes * 60 + seconds
                elif len(parts) == 2:  # MM:SS
                    minutes = int(parts[0])
                    seconds = int(parts[1])
                    return minutes * 60 + seconds
            
            # If nothing else works, try direct conversion
            return float(time_str)
            
        except Exception as e:
            print(f"Warning: Could not convert time '{time_str}': {e}")
            return np.nan
    
    def should_use_absolute_value(self, measurement_name):
        """Determine if measurement should use absolute values"""
        angle_measurements = [
            'C2-C7 Lordosis', 'C2–C7 Lordosis', 'C2-7 Lordosis',
            'T1 Slope', 'T1Slope', 
            'Lumbar Lordosis', 'LumbarLordosis',
            'Sacral Slope', 'SacralSlope',
            'Pelvic Tilt', 'PelvicTilt', 'Pelvic Incidence',
            'PI', 'PI (vector)'
        ]
        
        # Check if measurement name contains any of the angle measurement terms
        for angle_term in angle_measurements:
            if angle_term.lower() in measurement_name.lower():
                return True
        
        return False
    
    def calculate_icc_single_rater(self, method1_data, method2_data):
        """
        Calculate ICC(3,1) for single rater comparing two methods
        
        ICC(3,1): Two-way mixed model, single measurement, consistency agreement
        This is appropriate for comparing two measurement techniques by the same evaluator.
        
        Parameters:
        -----------
        method1_data : array-like
            Measurements from first method (Surgimap)
        method2_data : array-like
            Measurements from second method (SpineForge)
        
        Returns:
        --------
        dict: ICC results including ICC value, confidence interval, F-statistic, p-value
        """
        
        # Remove rows with missing data
        valid_indices = ~(np.isnan(method1_data) | np.isnan(method2_data))
        m1 = method1_data[valid_indices]
        m2 = method2_data[valid_indices]
        
        if len(m1) < 3:  # Need at least 3 observations
            return {
                'icc': np.nan,
                'lower_ci': np.nan,
                'upper_ci': np.nan,
                'f_stat': np.nan,
                'p_value': np.nan,
                'n_obs': len(m1),
                'interpretation': 'Insufficient data'
            }
        
        n = len(m1)
        
        # Create data matrix for ICC calculation
        data_matrix = np.column_stack([m1, m2])
        
        # Calculate means
        row_means = np.mean(data_matrix, axis=1)  # Subject means
        col_means = np.mean(data_matrix, axis=0)  # Method means
        grand_mean = np.mean(data_matrix)
        
        # Calculate Sum of Squares
        # Between subjects (rows)
        MSR = 2 * np.sum((row_means - grand_mean) ** 2) / (n - 1)
        
        # Between methods (columns) 
        MSC = n * np.sum((col_means - grand_mean) ** 2) / (2 - 1)
        
        # Error (residual)
        residuals = data_matrix - row_means.reshape(-1, 1) - col_means.reshape(1, -1) + grand_mean
        MSE = np.sum(residuals ** 2) / ((n - 1) * (2 - 1))
        
        # ICC(3,1) calculation - Two-way mixed, single measurement, consistency
        icc = (MSR - MSE) / (MSR + (2 - 1) * MSE + 2 * (MSC - MSE) / n)
        
        # F-statistic and p-value
        f_stat = MSR / MSE
        p_value = 1 - scipy_stats.f.cdf(f_stat, n - 1, (n - 1) * (2 - 1))
        
        # Confidence interval (approximate)
        alpha = 0.05
        f_lower = scipy_stats.f.ppf(alpha/2, n - 1, (n - 1) * (2 - 1))
        f_upper = scipy_stats.f.ppf(1 - alpha/2, n - 1, (n - 1) * (2 - 1))
        
        lower_ci = (MSR/MSE/f_upper - 1) / (MSR/MSE/f_upper + (2 - 1) + 2/n)
        upper_ci = (MSR/MSE/f_lower - 1) / (MSR/MSE/f_lower + (2 - 1) + 2/n)
        
        # Ensure CI bounds are reasonable
        lower_ci = max(0, lower_ci)
        upper_ci = min(1, upper_ci)
        
        # Interpretation
        if icc < 0.50:
            interpretation = "Poor reliability"
        elif icc < 0.75:
            interpretation = "Moderate reliability" 
        elif icc < 0.90:
            interpretation = "Good reliability"
        else:
            interpretation = "Excellent reliability"
        
        return {
            'icc': icc,
            'lower_ci': lower_ci,
            'upper_ci': upper_ci,
            'f_stat': f_stat,
            'p_value': p_value,
            'n_obs': n,
            'interpretation': interpretation,
            'MSR': MSR,
            'MSE': MSE,
            'MSC': MSC
        }
    
    def perform_complete_analysis(self):
        """Perform complete ICC analysis for all measurement pairs"""
        if self.data is None:
            print("✗ No data loaded. Please load data first.")
            return
        
        print("=" * 60)
        print("ICC ANALYSIS RESULTS - SURGIMAP vs SPINEFORGE PLANNER")
        print("=" * 60)
        print(f"Analysis Type: ICC(3,1) - Two-way mixed, single measurement, consistency")
        print(f"Sample Size: {len(self.data.columns)-1} cases")  # -1 for measurement name column
        print("=" * 60)
        
        # Store results
        icc_results = []
        
        for base_name, sm_row_idx, sp_row_idx in self.measurement_pairs:
            print(f"\n📏 MEASUREMENT: {base_name}")
            print("-" * 40)
            
            # Get raw data from rows (excluding first column which has measurement names)
            sm_data_raw = self.data.iloc[sm_row_idx, 1:]
            sp_data_raw = self.data.iloc[sp_row_idx, 1:]
            
            # Convert to float, handling potential string values
            sm_data = []
            sp_data = []
            
            for val in sm_data_raw:
                try:
                    sm_data.append(float(val))
                except (ValueError, TypeError):
                    sm_data.append(np.nan)
            
            for val in sp_data_raw:
                try:
                    sp_data.append(float(val))
                except (ValueError, TypeError):
                    sp_data.append(np.nan)
            
            sm_data = np.array(sm_data)
            sp_data = np.array(sp_data)
            
            # Apply absolute values for angle measurements
            if self.should_use_absolute_value(base_name):
                print(f"   Using absolute values for angle measurement")
                sm_data = np.abs(sm_data)
                sp_data = np.abs(sp_data)
            
            # Basic descriptive statistics
            sm_valid = sm_data[~np.isnan(sm_data)]
            sp_valid = sp_data[~np.isnan(sp_data)]
            
            print(f"Surgimap (SM):      Mean = {np.mean(sm_valid):.2f} ± {np.std(sm_valid):.2f}")
            print(f"SpineForge (SP):    Mean = {np.mean(sp_valid):.2f} ± {np.std(sp_valid):.2f}")
            
            # For paired comparison, we need both measurements to be valid
            valid_pairs = ~(np.isnan(sm_data) | np.isnan(sp_data))
            sm_paired = sm_data[valid_pairs]
            sp_paired = sp_data[valid_pairs]
            
            if len(sm_paired) > 0:
                print(f"Difference (SP-SM): Mean = {np.mean(sp_paired - sm_paired):.2f}")
            
            # Calculate ICC
            icc_result = self.calculate_icc_single_rater(sm_data, sp_data)
            
            print(f"\n🔍 ICC(3,1) Results:")
            print(f"   ICC = {icc_result['icc']:.3f} (95% CI: {icc_result['lower_ci']:.3f} - {icc_result['upper_ci']:.3f})")
            print(f"   F({icc_result['n_obs']-1}, {(icc_result['n_obs']-1)*1}) = {icc_result['f_stat']:.2f}, p = {icc_result['p_value']:.4f}")
            print(f"   Interpretation: {icc_result['interpretation']}")
            
            # Store for summary
            icc_results.append({
                'Measurement': base_name,
                'ICC': icc_result['icc'],
                'Lower_CI': icc_result['lower_ci'],
                'Upper_CI': icc_result['upper_ci'],
                'P_Value': icc_result['p_value'],
                'N_Obs': icc_result['n_obs'],
                'Interpretation': icc_result['interpretation'],
                'SM_Mean': np.mean(sm_valid),
                'SP_Mean': np.mean(sp_valid),
                'Mean_Diff': np.mean(sp_paired - sm_paired) if len(sm_paired) > 0 else np.nan,
                'Uses_Absolute': self.should_use_absolute_value(base_name)
            })
        
        # Store results
        self.results['icc_results'] = pd.DataFrame(icc_results)
        
        # Summary table
        print(f"\n📊 SUMMARY TABLE")
        print("=" * 60)
        if len(icc_results) > 0:
            summary_df = self.results['icc_results'][['Measurement', 'ICC', 'Lower_CI', 'Upper_CI', 'P_Value', 'Interpretation']]
            print(summary_df.to_string(index=False, float_format='%.3f'))
        else:
            print("No measurement pairs found in the data.")
        
    def analyze_measurement_times(self):
        """Analyze and compare measurement times between methods"""
        
        # Look for time measurements in rows
        measurement_names = self.data.iloc[:, 0].values
        sp_time_idx = None
        sm_time_idx = None
        
        for idx, name in enumerate(measurement_names):
            if isinstance(name, str):
                if 'SP- time' in name or 'SP - time' in name or 'time' in name.lower() and 'SP' in name:
                    sp_time_idx = idx
                elif 'SM- time' in name or 'SM - time' in name or 'time' in name.lower() and 'SM' in name:
                    sm_time_idx = idx
        
        if sp_time_idx is None or sm_time_idx is None:
            print("⚠️  Time measurements not found. Looking for any time-related rows...")
            
            # Show available row names for debugging
            print("Available measurements:")
            for idx, name in enumerate(measurement_names):
                if isinstance(name, str) and 'time' in name.lower():
                    print(f"   Row {idx}: {name}")
            
            print("⚠️  Skipping time analysis.")
            return
        
        print(f"\n⏱️  MEASUREMENT TIME ANALYSIS")
        print("=" * 60)
        
        # Get time data from rows (excluding first column) and convert to seconds
        sp_time_raw = self.data.iloc[sp_time_idx, 1:].values
        sm_time_raw = self.data.iloc[sm_time_idx, 1:].values
        
        # Convert time strings to seconds
        time_sp = []
        time_sm = []
        
        print("Converting time formats...")
        for val in sp_time_raw:
            converted = self.convert_time_to_seconds(val)
            time_sp.append(converted)
        
        for val in sm_time_raw:
            converted = self.convert_time_to_seconds(val)
            time_sm.append(converted)
        
        time_sp = np.array(time_sp)
        time_sm = np.array(time_sm)
        
        # Remove NaN values
        time_sp_clean = time_sp[~np.isnan(time_sp)]
        time_sm_clean = time_sm[~np.isnan(time_sm)]
        
        if len(time_sm_clean) == 0 or len(time_sp_clean) == 0:
            print("⚠️  No valid time data found after conversion.")
            return
        
        # Descriptive statistics
        print(f"Surgimap Time:      {np.mean(time_sm_clean):.1f} ± {np.std(time_sm_clean):.1f} seconds (n={len(time_sm_clean)})")
        print(f"SpineForge Time:    {np.mean(time_sp_clean):.1f} ± {np.std(time_sp_clean):.1f} seconds (n={len(time_sp_clean)})")
        
        # For paired comparison, we need valid pairs
        valid_pairs = ~(np.isnan(time_sp) | np.isnan(time_sm))
        
        if np.any(valid_pairs):
            paired_sp = time_sp[valid_pairs]
            paired_sm = time_sm[valid_pairs]
            print(f"Time Difference:    {np.mean(paired_sp - paired_sm):.1f} seconds")
            print(f"Time Reduction:     {(1 - np.mean(paired_sp)/np.mean(paired_sm))*100:.1f}%")
        
        # One-way ANOVA (as requested)
        f_stat, p_value = scipy_stats.f_oneway(time_sm_clean, time_sp_clean)
        
        print(f"\n🔬 One-way ANOVA Results:")
        print(f"   F-statistic = {f_stat:.3f}")
        print(f"   p-value = {p_value:.6f}")
        
        if p_value < 0.001:
            print(f"   Result: Highly significant difference (p < 0.001)")
        elif p_value < 0.01:
            print(f"   Result: Very significant difference (p < 0.01)")
        elif p_value < 0.05:
            print(f"   Result: Significant difference (p < 0.05)")
        else:
            print(f"   Result: No significant difference (p ≥ 0.05)")
        
        # Effect size (Cohen's d)
        pooled_std = np.sqrt(((len(time_sm_clean) - 1) * np.var(time_sm_clean) + 
                             (len(time_sp_clean) - 1) * np.var(time_sp_clean)) / 
                            (len(time_sm_clean) + len(time_sp_clean) - 2))
        cohens_d = (np.mean(time_sp_clean) - np.mean(time_sm_clean)) / pooled_std
        
        print(f"   Effect size (Cohen's d) = {cohens_d:.3f}")
        
        if abs(cohens_d) < 0.2:
            effect_interp = "Small effect"
        elif abs(cohens_d) < 0.5:
            effect_interp = "Small to medium effect"
        elif abs(cohens_d) < 0.8:
            effect_interp = "Medium to large effect"
        else:
            effect_interp = "Large effect"
        
        print(f"   Effect interpretation: {effect_interp}")
        
        # Store time results
        self.results['time_analysis'] = {
            'sm_mean': np.mean(time_sm_clean),
            'sp_mean': np.mean(time_sp_clean),
            'time_difference': np.mean(paired_sp - paired_sm) if np.any(valid_pairs) else np.nan,
            'time_reduction_percent': (1 - np.mean(time_sp_clean)/np.mean(time_sm_clean))*100,
            'f_statistic': f_stat,
            'p_value': p_value,
            'cohens_d': cohens_d,
            'effect_interpretation': effect_interp
        }
    
    def create_visualization(self):
        """Create comprehensive visualization of the analysis results"""
        
        if 'icc_results' not in self.results:
            print("⚠️  No ICC results to plot. Run analysis first.")
            return
        
        # Set up the plotting style
        plt.style.use('seaborn-v0_8')
        fig = plt.figure(figsize=(16, 12))
        
        # ICC Results Plot
        ax1 = plt.subplot(2, 3, (1, 2))
        icc_df = self.results['icc_results']
        
        # Create ICC plot with error bars
        y_pos = np.arange(len(icc_df))
        
        # Color code by reliability
        colors = []
        for icc in icc_df['ICC']:
            if icc < 0.50:
                colors.append('#e74c3c')  # Red - Poor
            elif icc < 0.75:
                colors.append('#f39c12')  # Orange - Moderate
            elif icc < 0.90:
                colors.append('#3498db')  # Blue - Good
            else:
                colors.append('#2ecc71')  # Green - Excellent
        
        # Plot ICC values with confidence intervals
        ax1.barh(y_pos, icc_df['ICC'], xerr=[icc_df['ICC'] - icc_df['Lower_CI'], 
                                            icc_df['Upper_CI'] - icc_df['ICC']], 
                color=colors, alpha=0.7, capsize=5)
        
        ax1.set_yticks(y_pos)
        ax1.set_yticklabels(icc_df['Measurement'])
        ax1.set_xlabel('ICC(3,1) Value')
        ax1.set_title('Intraclass Correlation Coefficients\nSurgimap vs SpineForge Planner', fontweight='bold')
        ax1.axvline(x=0.5, color='red', linestyle='--', alpha=0.5, label='Poor/Moderate')
        ax1.axvline(x=0.75, color='orange', linestyle='--', alpha=0.5, label='Moderate/Good')
        ax1.axvline(x=0.9, color='green', linestyle='--', alpha=0.5, label='Good/Excellent')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Measurement comparison scatter plots
        if len(self.measurement_pairs) >= 1:
            # First measurement
            ax2 = plt.subplot(2, 3, 3)
            base_name, sm_row_idx, sp_row_idx = self.measurement_pairs[0]
            
            # Get data from rows
            sm_data = self.data.iloc[sm_row_idx, 1:].values.astype(float)
            sp_data = self.data.iloc[sp_row_idx, 1:].values.astype(float)
            
            # Find valid pairs
            valid_pairs = ~(np.isnan(sm_data) | np.isnan(sp_data))
            sm_common = sm_data[valid_pairs]
            sp_common = sp_data[valid_pairs]
            
            if len(sm_common) > 1:
                ax2.scatter(sm_common, sp_common, alpha=0.6, s=50)
                
                # Add identity line
                min_val = min(sm_common.min(), sp_common.min())
                max_val = max(sm_common.max(), sp_common.max())
                ax2.plot([min_val, max_val], [min_val, max_val], 'r--', alpha=0.8, label='Perfect Agreement')
                
                # Add regression line
                if len(sm_common) > 2:
                    slope, intercept, r_value, p_value, std_err = scipy_stats.linregress(sm_common, sp_common)
                    line = slope * np.array([min_val, max_val]) + intercept
                    ax2.plot([min_val, max_val], line, 'b-', alpha=0.8, label=f'Regression (r={r_value:.3f})')
                
                ax2.set_xlabel(f'{base_name} - Surgimap')
                ax2.set_ylabel(f'{base_name} - SpineForge')
                ax2.set_title(f'{base_name}\nMethod Comparison')
                ax2.legend()
                ax2.grid(True, alpha=0.3)
            else:
                ax2.text(0.5, 0.5, 'Insufficient data\nfor scatter plot', 
                        ha='center', va='center', transform=ax2.transAxes)
                ax2.set_title(f'{base_name}\nMethod Comparison')
        
        # Time analysis plot (if available)
        if 'time_analysis' in self.results:
            ax3 = plt.subplot(2, 3, 4)
            
            # Look for time data in rows
            measurement_names = self.data.iloc[:, 0].values
            sp_time_idx = None
            sm_time_idx = None
            
            for idx, name in enumerate(measurement_names):
                if isinstance(name, str):
                    if 'SP- time' in name or 'SP - time' in name or ('time' in name.lower() and 'SP' in name):
                        sp_time_idx = idx
                    elif 'SM- time' in name or 'SM - time' in name or ('time' in name.lower() and 'SM' in name):
                        sm_time_idx = idx
            
            if sp_time_idx is not None and sm_time_idx is not None:
                sp_time_raw = self.data.iloc[sp_time_idx, 1:].values
                sm_time_raw = self.data.iloc[sm_time_idx, 1:].values
                
                # Convert time strings to seconds
                time_sp = []
                time_sm = []
                
                for val in sp_time_raw:
                    converted = self.convert_time_to_seconds(val)
                    time_sp.append(converted)
                
                for val in sm_time_raw:
                    converted = self.convert_time_to_seconds(val)
                    time_sm.append(converted)
                
                time_sp = np.array(time_sp)
                time_sm = np.array(time_sm)
                
                # Remove NaN values
                time_sp_clean = time_sp[~np.isnan(time_sp)]
                time_sm_clean = time_sm[~np.isnan(time_sm)]
                
                if len(time_sp_clean) > 0 and len(time_sm_clean) > 0:
                    # Box plot
                    data_to_plot = [time_sm_clean, time_sp_clean]
                    labels = ['Surgimap', 'SpineForge']
                    bp = ax3.boxplot(data_to_plot, labels=labels, patch_artist=True)
                    
                    # Color the boxes
                    colors = ['#3498db', '#e74c3c']
                    for patch, color in zip(bp['boxes'], colors):
                        patch.set_facecolor(color)
                        patch.set_alpha(0.7)
                    
                    ax3.set_ylabel('Time (seconds)')
                    ax3.set_title('Measurement Time Comparison')
                    ax3.grid(True, alpha=0.3)
                    
                    # Add mean values as text
                    ax3.text(1, np.mean(time_sm_clean), f'Mean: {np.mean(time_sm_clean):.1f}s', 
                            ha='center', va='bottom', fontweight='bold')
                    ax3.text(2, np.mean(time_sp_clean), f'Mean: {np.mean(time_sp_clean):.1f}s', 
                            ha='center', va='bottom', fontweight='bold')
                else:
                    ax3.text(0.5, 0.5, 'No time data\navailable', 
                            ha='center', va='center', transform=ax3.transAxes)
            else:
                ax3.text(0.5, 0.5, 'Time measurements\nnot found', 
                        ha='center', va='center', transform=ax3.transAxes)
        
        # Bland-Altman plot (if we have paired data)
        if len(self.measurement_pairs) >= 1:
            ax4 = plt.subplot(2, 3, 5)
            base_name, sm_row_idx, sp_row_idx = self.measurement_pairs[0]
            
            # Get data from rows
            sm_data = self.data.iloc[sm_row_idx, 1:].values.astype(float)
            sp_data = self.data.iloc[sp_row_idx, 1:].values.astype(float)
            
            # Find valid pairs
            valid_pairs = ~(np.isnan(sm_data) | np.isnan(sp_data))
            sm_common = sm_data[valid_pairs]
            sp_common = sp_data[valid_pairs]
            
            if len(sm_common) > 2:
                # Bland-Altman calculations
                mean_values = (sm_common + sp_common) / 2
                diff_values = sp_common - sm_common
                
                mean_diff = np.mean(diff_values)
                std_diff = np.std(diff_values)
                
                ax4.scatter(mean_values, diff_values, alpha=0.6, s=50)
                ax4.axhline(mean_diff, color='red', linestyle='-', label=f'Mean Diff: {mean_diff:.2f}')
                ax4.axhline(mean_diff + 1.96 * std_diff, color='red', linestyle='--', 
                           label=f'+1.96 SD: {mean_diff + 1.96 * std_diff:.2f}')
                ax4.axhline(mean_diff - 1.96 * std_diff, color='red', linestyle='--', 
                           label=f'-1.96 SD: {mean_diff - 1.96 * std_diff:.2f}')
                
                ax4.set_xlabel(f'Mean of {base_name} (SM + SP)/2')
                ax4.set_ylabel(f'Difference (SP - SM)')
                ax4.set_title(f'Bland-Altman Plot\n{base_name}')
                ax4.legend()
                ax4.grid(True, alpha=0.3)
            else:
                ax4.text(0.5, 0.5, 'Insufficient data\nfor Bland-Altman plot', 
                        ha='center', va='center', transform=ax4.transAxes)
                ax4.set_title(f'Bland-Altman Plot\n{base_name}')
        
        # Summary statistics table
        ax5 = plt.subplot(2, 3, 6)
        ax5.axis('tight')
        ax5.axis('off')
        
        # Create summary table data
        if 'icc_results' in self.results:
            table_data = []
            for _, row in self.results['icc_results'].iterrows():
                table_data.append([
                    row['Measurement'],
                    f"{row['ICC']:.3f}",
                    f"({row['Lower_CI']:.3f}, {row['Upper_CI']:.3f})",
                    row['Interpretation'].split()[0]  # Just first word
                ])
            
            table = ax5.table(cellText=table_data,
                            colLabels=['Measurement', 'ICC', '95% CI', 'Rating'],
                            cellLoc='center',
                            loc='center')
            table.auto_set_font_size(False)
            table.set_fontsize(9)
            table.scale(1.2, 1.5)
            
            # Color code the table
            for i in range(1, len(table_data) + 1):
                icc_val = float(table_data[i-1][1])
                if icc_val < 0.50:
                    color = '#ffebee'  # Light red
                elif icc_val < 0.75:
                    color = '#fff3e0'  # Light orange
                elif icc_val < 0.90:
                    color = '#e3f2fd'  # Light blue
                else:
                    color = '#e8f5e8'  # Light green
                
                for j in range(4):
                    table[(i, j)].set_facecolor(color)
        
        plt.suptitle('SpineForge Planner vs Surgimap - Reliability Analysis', 
                    fontsize=16, fontweight='bold')
        plt.tight_layout()
        plt.show()
    
    def export_results(self, filename='ICC_Analysis_Results.xlsx'):
        """Export all results to Excel file"""
        
        if not self.results:
            print("⚠️  No results to export. Run analysis first.")
            return
        
        try:
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                
                # ICC Results
                if 'icc_results' in self.results:
                    self.results['icc_results'].to_excel(writer, sheet_name='ICC_Results', index=False)
                
                # Raw data
                if self.data is not None:
                    self.data.to_excel(writer, sheet_name='Raw_Data', index=False)
                
                # Time analysis results
                if 'time_analysis' in self.results:
                    time_df = pd.DataFrame([self.results['time_analysis']])
                    time_df.to_excel(writer, sheet_name='Time_Analysis', index=False)
            
            print(f"✓ Results exported to: {filename}")
            
        except Exception as e:
            print(f"✗ Error exporting results: {e}")


def main():
    """Main function to run the analysis"""
    
    print("🏥 SpineForge Planner - ICC Reliability Analysis")
    print("=" * 50)
    
    # Initialize analyzer
    analyzer = ICCAnalyzer()
    
    # Load data - update this path to your actual data file
    data_file = "Measurements - CleanWorksheet.csv"  # Update this path
    
    if not analyzer.load_data(data_file):
        print("❌ Failed to load data. Please check the file path and format.")
        return
    
    # Perform ICC analysis
    analyzer.perform_complete_analysis()
    
    # Analyze measurement times
    analyzer.analyze_measurement_times()
    
    # Create visualizations
    analyzer.create_visualization()
    
    # Export results
    analyzer.export_results("SpineForge_vs_Surgimap_ICC_Analysis.xlsx")
    
    print(f"\n✅ Analysis completed successfully!")
    print(f"📊 Key Findings Summary:")
    if 'icc_results' in analyzer.results:
        excellent_count = sum(1 for icc in analyzer.results['icc_results']['ICC'] if icc >= 0.90)
        good_count = sum(1 for icc in analyzer.results['icc_results']['ICC'] if 0.75 <= icc < 0.90)
        moderate_count = sum(1 for icc in analyzer.results['icc_results']['ICC'] if 0.50 <= icc < 0.75)
        poor_count = sum(1 for icc in analyzer.results['icc_results']['ICC'] if icc < 0.50)
        
        print(f"   • Excellent reliability: {excellent_count} measurements")
        print(f"   • Good reliability: {good_count} measurements") 
        print(f"   • Moderate reliability: {moderate_count} measurements")
        print(f"   • Poor reliability: {poor_count} measurements")
    
    if 'time_analysis' in analyzer.results:
        time_reduction = analyzer.results['time_analysis']['time_reduction_percent']
        print(f"   • Average time reduction: {time_reduction:.1f}%")


if __name__ == "__main__":
    main()