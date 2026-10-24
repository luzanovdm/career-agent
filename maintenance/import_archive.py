"""Bounded streaming preservation for the separate offline legacy importer."""
from dataclasses import asdict,dataclass
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
from career.contracts import CareerError,canonical,digest,require

MiB=1024*1024


@dataclass(frozen=True)
class ImportLimits:
    state_bytes:int=256*MiB
    file_bytes:int=512*MiB
    total_bytes:int=12*1024*MiB
    entries:int=200000
    reference_bytes:int=MiB
    records:int=1000000
    groups:int=256
    archive_bytes:int=12*1024*MiB
    report_bytes:int=128*MiB
    chunk_bytes:int=8*MiB
    archive_chunks:int=2048
    memory_bytes:int=4*1024*MiB
    seconds:int=1800

    def validate(self):
        ceiling=ImportLimits()
        for key,value in asdict(self).items():
            require(type(value) is int and 0<value<=getattr(ceiling,key),'INVALID_LIMIT','Import limits must be positive and cannot exceed the documented hard ceiling: '+key)
        require(self.chunk_bytes>=65536 and self.report_bytes>=65536,'INVALID_LIMIT','Chunks and reports require at least 64 KiB to keep metadata/resource growth bounded')
        return self


def file_hash(path,maximum):
    before=path.stat();require(before.st_size<=maximum,'IMPORT_RESOURCE_LIMIT','File exceeds bounded import size')
    h=hashlib.sha256();count=0
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(MiB),b''):
            count+=len(block);require(count<=maximum,'IMPORT_RESOURCE_LIMIT','File grew beyond bounded import size');h.update(block)
    after=path.stat()
    require((before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns) and count==before.st_size,'SOURCE_CHANGED','Source changed during bounded read')
    return h.hexdigest()


def inventory(source,limits=None):
    limits=(limits or ImportLimits()).validate();source=Path(source);rows=[];total=entries=0
    for path in sorted(source.rglob('*')):
        entries+=1;require(entries<=limits.entries,'IMPORT_RESOURCE_LIMIT','Source exceeds entry-count limit')
        if path.is_dir() and not path.is_symlink():continue
        relative=path.relative_to(source).as_posix()
        if path.is_symlink():
            target=path.resolve()
            if not target.is_relative_to(source.resolve()) or not target.is_file():
                rows.append(dict(path=relative,kind='symlink',target=os.readlink(path),status='quarantined',reason='Link leaves source or cannot resolve'));continue
        require(path.is_file(),'UNSUPPORTED_SOURCE','Source contains nonregular content')
        size=path.stat().st_size;total+=size
        require(total<=limits.total_bytes,'IMPORT_RESOURCE_LIMIT','Source exceeds cumulative byte limit')
        rows.append(dict(path=relative,kind='symlink' if path.is_symlink() else 'file',size=size,sha256=file_hash(path,limits.file_bytes),**({'target':os.readlink(path)} if path.is_symlink() else {})))
    return rows


class ChunkWriter(io.RawIOBase):
    def __init__(self,repository,limits):
        self.repository=repository;self.limits=limits;self.buffer=bytearray();self.objects=[];self.chunks=[];self.sha=hashlib.sha256();self.size=0

    def writable(self):return True

    def write(self,data):
        value=memoryview(data);length=len(value);self.size+=length
        require(self.size<=self.limits.archive_bytes,'IMPORT_RESOURCE_LIMIT','Compressed original archive exceeds its byte limit')
        self.sha.update(value)
        while value:
            count=min(len(value),self.limits.chunk_bytes-len(self.buffer));self.buffer.extend(value[:count]);value=value[count:]
            if len(self.buffer)==self.limits.chunk_bytes:self.publish()
        return length

    def publish(self):
        if not self.buffer:return
        require(len(self.chunks)<self.limits.archive_chunks,'IMPORT_RESOURCE_LIMIT','Original archive exceeds its bounded chunk count')
        obj=self.repository.publish(bytes(self.buffer),'bin','application/octet-stream');self.objects.append(obj)
        self.chunks.append(dict(artifact_id=obj['id'],sha256=obj['sha256'],size=obj['size']));self.buffer.clear()


class CheckedReader:
    def __init__(self,stream):self.stream=stream;self.sha=hashlib.sha256();self.size=0
    def read(self,count):
        data=self.stream.read(count);self.sha.update(data);self.size+=len(data);return data


def preserve_originals(repository,source,entries,limits):
    """One gzip/tar stream preserves all bytes, including oversized originals and safe link metadata."""
    writer=ChunkWriter(repository,limits)
    with gzip.GzipFile(filename='',fileobj=writer,mode='wb',mtime=0,compresslevel=1) as zipped:
        with tarfile.open(fileobj=zipped,mode='w|',format=tarfile.PAX_FORMAT) as archive:
            for entry in entries:
                info=tarfile.TarInfo(entry['path']);info.mode=0o600;info.mtime=0
                if entry['kind']=='symlink':
                    info.type=tarfile.SYMTYPE;info.linkname=entry['target'];archive.addfile(info);continue
                path=source/entry['path'];info.size=entry['size']
                with path.open('rb') as stream:
                    checked=CheckedReader(stream);archive.addfile(info,checked)
                    require(checked.size==entry['size'] and checked.sha.hexdigest()==entry['sha256'],'SOURCE_CHANGED','Original bytes changed while archiving')
    writer.publish()
    manifest=dict(format='career-agent.import-originals/1',encoding='gzip-tar',archive_sha256=writer.sha.hexdigest(),archive_bytes=writer.size,source_inventory_sha256=digest(entries),entries=len(entries),chunks=writer.chunks)
    obj=repository.publish(canonical(manifest).encode(),'json','application/vnd.career-agent.import-originals+json');writer.objects.append(obj)
    return dict(manifest_artifact_id=obj['id'],manifest_sha256=obj['sha256'],**manifest),writer.objects


def write_report(path,value,limits):
    # Stream JSON output; a large inventory never needs a second complete serialized copy.
    temporary=path.with_name(path.name+'.new');size=0
    with temporary.open('xb') as output:
        for part in json.JSONEncoder(ensure_ascii=False,sort_keys=True,separators=(',',':')).iterencode(value):
            data=part.encode();size+=len(data);require(size<=limits.report_bytes,'IMPORT_RESOURCE_LIMIT','Import report exceeds its bounded byte limit');output.write(data)
        output.flush();os.fsync(output.fileno())
    temporary.chmod(0o600);os.replace(temporary,path)


class ChunkReader(io.RawIOBase):
    def __init__(self,snapshot,chunks):
        self.snapshot=snapshot;self.chunks=iter(chunks);self.current=None;self.sha=hashlib.sha256();self.size=0

    def readable(self):return True

    def read(self,count=-1):
        require(0<=count<=MiB,'IMPORT_RESOURCE_LIMIT','Archive verification requires bounded reads')
        output=bytearray()
        while len(output)<count:
            if self.current is None:
                try:chunk=next(self.chunks)
                except StopIteration:break
                row,path=self.snapshot.object(chunk['artifact_id'])
                require(row['sha256']==chunk['sha256'] and row['size']==chunk['size'],'MATERIAL_CHANGED','Original archive chunk binding changed')
                self.current=path.open('rb')
            part=self.current.read(count-len(output))
            if not part:self.current.close();self.current=None;continue
            output.extend(part)
        self.sha.update(output);self.size+=len(output);return bytes(output)

    def close(self):
        if self.current:self.current.close()
        super().close()


def verify_originals(repository,manifest,entries,limits):
    """Read back every archived original without extracting paths or hydrating the archive."""
    expected={entry['path']:entry for entry in entries};seen=set();expanded=0
    with repository.open() as snapshot:
        reader=ChunkReader(snapshot,manifest['chunks'])
        try:
            with tarfile.open(fileobj=reader,mode='r|gz') as archive:
                for member in archive:
                    require(member.name in expected and member.name not in seen,'ARCHIVE_INTEGRITY','Unexpected or duplicate original archive member')
                    entry=expected[member.name];seen.add(member.name)
                    if entry['kind']=='symlink':
                        require(member.issym() and member.linkname==entry['target'],'ARCHIVE_INTEGRITY','Original symlink metadata changed');continue
                    require(member.isfile() and member.size==entry['size'],'ARCHIVE_INTEGRITY','Original archive size/type changed')
                    expanded+=member.size;require(expanded<=limits.total_bytes,'IMPORT_RESOURCE_LIMIT','Original archive expansion exceeds explicit limit')
                    h=hashlib.sha256()
                    with archive.extractfile(member) as stream:
                        for block in iter(lambda:stream.read(MiB),b''):h.update(block)
                    require(h.hexdigest()==entry['sha256'],'ARCHIVE_INTEGRITY','Original archived bytes do not match inventory')
            while reader.read(MiB):pass
            require(len(seen)==len(expected) and reader.sha.hexdigest()==manifest['archive_sha256'] and reader.size==manifest['archive_bytes'],'ARCHIVE_INTEGRITY','Original archive stream or inventory coverage changed')
        finally:reader.close()
    return dict(verified=True,files=len(seen),original_bytes=expanded,archive_bytes=manifest['archive_bytes'],source_inventory_sha256=digest(entries))
