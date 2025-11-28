import streamlit as st
import pandas as pd
import io
import re

# --- Configuration and Setup ---
# Set the page configuration for a wider layout
st.set_page_config(layout="wide", page_title="Column-Agnostic Data Explorer")

# Define the threshold for unique values to trigger a multiselect dropdown
UNIQUE_VALUE_THRESHOLD = 50 

def load_data(uploaded_file):
    """Loads CSV or Excel data into a Pandas DataFrame."""
    try:
        if uploaded_file.name.endswith('.csv'):
            # Use io.TextIOWrapper to read CSV, allowing universal newline mode
            df = pd.read_csv(io.TextIOWrapper(uploaded_file, encoding='utf-8'))
        elif uploaded_file.name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(uploaded_file)
        else:
            st.error("Unsupported file format. Please upload a CSV or Excel file.")
            return None
        return df
    except Exception as e:
        st.error(f"Error loading file: {e}")
        return None

def main():
    """Main function to run the Streamlit application."""
    st.title("📊 Data Filtering Tool")
    st.markdown("Upload your CSV or Excel file to begin filtering and exploring the data.")

    # 1. File Uploader
    uploaded_file = st.file_uploader(
        "Choose a CSV or Excel File",
        type=['csv', 'xlsx', 'xls'],
        help="Upload any structured data file to instantly get filtering tools."
    )

    if uploaded_file is None:
        st.info("Awaiting file upload...")
        return

    df = load_data(uploaded_file)
    if df is None:
        return

    # Initialize the filtered DataFrame with the original data
    df_filtered = df.copy()

    # --- 2. Dynamic Filtering Section ---
    st.sidebar.header("Data Filters")
    st.sidebar.markdown(f"**Loaded:** `{uploaded_file.name}`")
    st.sidebar.markdown(f"**Rows:** {len(df)} | **Columns:** {len(df.columns)}")
    st.sidebar.markdown("---")

    st.subheader("Filter Settings")

    # Dynamic column filtering containers (using columns for better layout)
    num_cols_to_display = 4
    filter_columns = st.columns(num_cols_to_display)
    
    col_index = 0
    
    # Iterate through all columns in the DataFrame
    for column in df.columns:
        # Place the filter widget in the next available column container
        with filter_columns[col_index % num_cols_to_display]:
            
            # Identify unique values and count
            unique_values = df[column].dropna().astype(str).unique()
            n_unique = len(unique_values)

            # Check if the column is suitable for a multi-select dropdown
            if n_unique <= UNIQUE_VALUE_THRESHOLD and n_unique > 0:
                # 3. Dropdown/Multi-select for low unique values
                st.caption(f"Categorical Filter ({n_unique} unique)")
                selected_values = st.multiselect(
                    f"Select values for '{column}'",
                    options=unique_values,
                    default=[]
                )

                # Apply filter: if selections are made, filter the DataFrame
                if selected_values:
                    # Convert column data to string for consistent comparison
                    df_filtered = df_filtered[df_filtered[column].astype(str).isin(selected_values)]
            
            else:
                # 2. Text Input for high unique values or general search
                st.caption("Search Filter (Use regex, e.g., `^A` or `.*ing`)")
                search_term = st.text_input(
                    f"Search in '{column}'",
                    placeholder="Enter search string or regex...",
                    key=f"search_{column}"
                )

                # Apply filter: if a search term is provided, filter the DataFrame
                if search_term:
                    try:
                        # Use a case-insensitive regex search
                        df_filtered = df_filtered[
                            df_filtered[column].astype(str).str.contains(search_term, case=False, na=False, regex=True)
                        ]
                    except re.error:
                        st.error(f"Invalid Regular Expression used in '{column}' filter.")
                        # Stop filtering if regex is invalid
                        return

        col_index += 1
        
    st.markdown("---")


    # --- 4. Dashboard Display ---
    st.subheader("Filtered Data Dashboard")
    
    # Display statistics
    st.metric(
        label="Total Rows Remaining", 
        value=f"{len(df_filtered):,}",
        delta=f"- {len(df) - len(df_filtered):,} rows filtered out",
        delta_color="inverse"
    )

    if len(df_filtered) == 0:
        st.warning("No data matches the current filter criteria.")
    else:
        # Display the filtered data table
        st.dataframe(df_filtered, use_container_width=True, height=500)

        # Optional: Allow download of the filtered data
        csv_export = df_filtered.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download Filtered Data as CSV",
            data=csv_export,
            file_name='filtered_data.csv',
            mime='text/csv',
            help="Click here to download the currently filtered dataset."
        )


if __name__ == "__main__":
    main()