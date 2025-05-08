import pandas as pd

# Paths
input_path  = 'merged-file.parquet'
output_path = 'merged-file-renamed.parquet'

# 1. Load (requires pyarrow or fastparquet)
df = pd.read_parquet(input_path)

# 2. Cast the 'index' column to datetime64
df['index'] = pd.to_datetime(df['index'])

# (Optional) If you want that as the DataFrame index:
# df.set_index('index', inplace=True)

# 3. Build rename map for numeric-named columns
mapping = {col: f'h{col}' for col in df.columns if col.isdigit()}

# 4. Rename
df.rename(columns=mapping, inplace=True)

# 5. Write back
df.to_parquet(output_path, index=False)

print("Casted 'index' to datetime64 and renamed columns:")
print(mapping)
print(f"Saved to {output_path}")
