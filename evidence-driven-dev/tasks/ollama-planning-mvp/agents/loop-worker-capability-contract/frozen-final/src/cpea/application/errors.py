class DependencyUnavailable(RuntimeError):
    code = 'sql_executor_unavailable'
    def __init__(self):
        super().__init__('SQL execution requires an explicitly injected executor and datasource binding.')
