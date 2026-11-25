import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
from scripts import portable_install as p

def commit(root):
    subprocess.run(["git","-C",str(root),"add","-A"],check=True)
    subprocess.run(["git","-C",str(root),"-c","user.name=Fixture","-c","user.email=fixture@example.invalid","commit","-qm","fixture"],check=True)

def init(root):
    root.mkdir()
    subprocess.run(["git","init","-q","-b","main",str(root)],check=True)

def write(root,name,data):
    f=root/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text(data)

class PortableMigrationTests(unittest.TestCase):
    def test_fresh_v1_alpha_core_and_pro_migration(self):
        for version in (None,"2.0.0-alpha.1","2.0.0-rc.1"):
            with self.subTest(version=version), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);src=root/"src";dst=root/"dst";init(src);init(dst)
                write(src,"VERSION","2.0.0-rc.1\n");write(src,"scripts/pro_assistant.py","fixture backend")
                write(dst,"README.md","# PostForge AI\n")
                write(dst,".github/workflows/publish.yml","name: PostForge Publisher\n")
                if version:write(dst,"VERSION",version+"\n")
                if version=="2.0.0-rc.1":write(dst,"scripts/pro_assistant.py","previous backend")
                for path in ("queue/a.json","state/a.json","studio/drafts/a.json","scheduled/a.json"):
                    write(dst,path,"protected fixture")
                commit(src);commit(dst)
                with patch.object(p,"FILES",("VERSION","scripts/pro_assistant.py")):
                    plan=p.plan(dst,src);before=p.protected(dst)
                    with self.assertRaises(ValueError):p.apply(dst,src,"0"*64,verify=False)
                    p.apply(dst,src,plan["plan_sha256"],verify=False)
                    self.assertEqual(p.protected(dst),before)
                    self.assertEqual((dst/"scripts/pro_assistant.py").read_text(),"fixture backend")
    def test_test_failure_rolls_back_and_dirty_tree_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/"src";dst=root/"dst";init(src);init(dst)
            write(src,"VERSION","2.0.0-rc.1");write(src,"scripts/pro_assistant.py","new")
            write(dst,"README.md","# PostForge AI\n");write(dst,".github/workflows/publish.yml","name: PostForge Publisher")
            commit(src);commit(dst)
            with patch.object(p,"FILES",("VERSION","scripts/pro_assistant.py")):
                plan=p.plan(dst,src)
                with patch.object(p.subprocess,"run",side_effect=subprocess.CalledProcessError(1,"tests")):
                    with self.assertRaises(subprocess.CalledProcessError):p.apply(dst,src,plan["plan_sha256"])
                self.assertFalse((dst/"VERSION").exists())
                self.assertFalse((dst/"scripts/pro_assistant.py").exists())
                self.assertEqual(p.git(dst,"status","--porcelain"),"")
                write(dst,"README.md","dirty")
                with self.assertRaises(ValueError):p.plan(dst,src)
