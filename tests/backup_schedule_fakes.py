"""In-memory boundary doubles for schedule/storage integration tests."""
from types import SimpleNamespace
from test_import_backup import Database, Query


class ScheduleQuery(Query):
    def __init__(self, db, table):
        super().__init__(db, table)
        self.update_values = None
        self.deleting = False
        self.desc = False
    def order(self, field, desc=False):
        self.desc = desc
        return super().order(field)
    def update(self, values):
        self.update_values = values
        return self
    def delete(self):
        self.deleting = True
        return self
    def neq(self, field, value):
        self.filters.append(('neq',field,value)); return self
    def lt(self, field, value):
        self.filters.append(('lt',field,value)); return self
    def execute(self):
        if self.table not in {'import_backup_schedules','import_backup_artifacts'}:
            return super().execute()
        rows=self.db.rows.setdefault(self.table,[])
        selected=rows[:]
        for op,key,value in self.filters:
            selected=[row for row in selected if ((op=='eq' and row.get(key)==value) or (op=='neq' and row.get(key)!=value) or (op=='lt' and row.get(key)<value) or (op=='lte' and row.get(key)<=value))]
        if self.payload is not None:
            row=dict(self.payload);row.setdefault('id','00000000-0000-0000-0000-000000000001');rows.append(row);return SimpleNamespace(data=[row])
        if self.update_values is not None:
            for row in selected: row.update(self.update_values)
        if self.deleting:
            self.db.rows[self.table]=[row for row in rows if row not in selected]
        if self.orders:
            selected.sort(key=lambda row:tuple(row.get(key) for key in self.orders),reverse=self.desc)
        return SimpleNamespace(data=selected[:self.size])


class MemoryStorage:
    def __init__(self): self.objects={}
    def from_(self, bucket):
        assert bucket=='import-backups'
        return self
    def upload(self,path,reader,options):
        assert path not in self.objects
        self.objects[path]=reader.read()
    def download(self,path): return self.objects[path]
    def remove(self,paths):
        for path in paths: self.objects.pop(path,None)


class ScheduleDatabase(Database):
    def __init__(self, sales=None):
        super().__init__(sales)
        self.storage=MemoryStorage()
    def table(self, name): return ScheduleQuery(self,name)
