import tempfile
import unittest
from pathlib import Path

from fluxfile_core import Engine, Job, create_job
from fluxfile_queue import filter_jobs, job_matches, requeue_job, requeue_problems, remove_completed


class QueueOperationTests(unittest.TestCase):
    def test_filter_searches_paths_routes_engine_status_output_and_error(self):
        jobs=[
            Job("1","/tmp/photos/cat.png","png","webp",status="Done",engine="pillow",output="/tmp/out/cat.webp",relative_dir="photos"),
            Job("2","/tmp/docs/report.docx","docx","pdf",status="Failed",engine="libreoffice",error="converter timeout",relative_dir="docs"),
            Job("3","/tmp/missing.csv","csv","xlsx",status="Missing",engine="unavailable",error="Source file is missing"),
        ]
        self.assertEqual([j.id for j in filter_jobs(jobs,"cat","all")],["1"])
        self.assertEqual([j.id for j in filter_jobs(jobs,"timeout","problems")],["2"])
        self.assertEqual([j.id for j in filter_jobs(jobs,"csv","missing")],["3"])
        self.assertTrue(job_matches(jobs[0],"webp","done"))
        self.assertFalse(job_matches(jobs[0],"","problems"))

    def test_requeue_job_revives_existing_source_and_keeps_missing_explicit(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            source=root/"note.txt"
            source.write_text("hello")
            engine=Engine()

            existing=create_job(source,"txt",engine)
            existing.status="Failed"
            existing.error="old failure"
            requeue_job(existing,engine)
            self.assertEqual(existing.status,"Queued")
            self.assertEqual(existing.error,"")

            missing=Job("missing",str(root/"gone.txt"),"txt","txt",status="Failed",engine="copy")
            requeue_job(missing,engine)
            self.assertEqual(missing.status,"Missing")
            self.assertEqual(missing.engine,"unavailable")

    def test_retry_problems_ignores_done_and_queued_jobs(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            engine=Engine()
            a=root/"a.txt";a.write_text("a")
            b=root/"b.txt";b.write_text("b")
            c=root/"c.txt";c.write_text("c")
            done=create_job(a,"txt",engine);done.status="Done"
            queued=create_job(b,"txt",engine);queued.status="Queued"
            failed=create_job(c,"txt",engine);failed.status="Failed"

            requeued,unresolved=requeue_problems([done,queued,failed],engine)
            self.assertEqual((requeued,unresolved),(1,0))
            self.assertEqual(done.status,"Done")
            self.assertEqual(queued.status,"Queued")
            self.assertEqual(failed.status,"Queued")

    def test_remove_completed_only_removes_done(self):
        jobs=[
            Job("1","a","txt","txt",status="Done"),
            Job("2","b","txt","txt",status="Failed"),
            Job("3","c","txt","txt",status="Skipped"),
        ]
        kept,removed=remove_completed(jobs)
        self.assertEqual(removed,1)
        self.assertEqual([job.id for job in kept],["2","3"])


if __name__=="__main__":
    unittest.main()
