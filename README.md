# TPCH-Benchmark-for-DuckDB

For this benchmarking, I have used DuckDB and used the filter complexity dimension. For the configuration, I choose In-memory vs on-disk database as a discrete option and vary the size
of the dataset(scale factors-0.1,1,3) as the continuous option. Using these two configurations helps to understand how the volume of data and complexity of the queries influence the performance of the in-memory and on-disk databases.
