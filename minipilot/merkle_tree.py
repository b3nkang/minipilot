
from typing import Dict, Set, List
from pathlib import Path
import hashlib
from pymerkle import InmemoryTree


class FileChangeDetector:
    def __init__(self):
        self.tree = InmemoryTree()
        self.file_hashes: Dict[str, str] = {}
        self.current_root_hash = ""
    
    def build_tree_from_files(self, file_hashes: Dict[str, str]):
        self.file_hashes = file_hashes.copy()
        
        self.tree = InmemoryTree()
        
        for file_path in sorted(file_hashes.keys()):
            file_hash = file_hashes[file_path]
            entry = f"{file_path}:{file_hash}".encode()
            self.tree.append_entry(entry)
        
        try:
            has_records = len(file_hashes) > 0
            self.current_root_hash = self.tree.root.hex() if has_records else ""
        except Exception:
            self.current_root_hash = ""
    
    def get_root_hash(self) -> str:
        return self.current_root_hash
    
    def detect_changes(self, new_file_hashes: Dict[str, str]) -> Dict[str, Set[str]]:
        old_files = set(self.file_hashes.keys())
        new_files = set(new_file_hashes.keys())
        
        added = new_files - old_files
        deleted = old_files - new_files
        modified = set()
        
        common_files = old_files & new_files
        for file_path in common_files:
            if self.file_hashes[file_path] != new_file_hashes[file_path]:
                modified.add(file_path)
        
        return {
            'added': added,
            'modified': modified,
            'deleted': deleted
        }
    
    def has_changes(self, new_file_hashes: Dict[str, str]) -> bool:
        temp_tree = InmemoryTree()
        
        for file_path in sorted(new_file_hashes.keys()):
            file_hash = new_file_hashes[file_path]
            entry = f"{file_path}:{file_hash}".encode()
            temp_tree.append_entry(entry)
        
        try:
            has_records = len(new_file_hashes) > 0
            new_root_hash = temp_tree.root.hex() if has_records else ""
        except Exception:
            new_root_hash = ""
        return new_root_hash != self.current_root_hash
    
    def update_tree(self, new_file_hashes: Dict[str, str]) -> bool:
        old_root_hash = self.current_root_hash
        self.build_tree_from_files(new_file_hashes)
        return old_root_hash != self.current_root_hash
    
    def get_changed_files(self, new_file_hashes: Dict[str, str]) -> Set[str]:
        changes = self.detect_changes(new_file_hashes)
        return changes['added'] | changes['modified'] | changes['deleted']