using System.Collections.Concurrent;
using Newtonsoft.Json.Linq;
using Rhino;

namespace RhinoMcp.Handlers
{
    /// <summary>
    /// Frame-sequence render queue.
    ///
    /// Submitted jobs run on a background <see cref="System.Threading.Tasks.Task"/> that
    /// dispatches each frame back onto the Rhino UI thread for capture. The
    /// minimal v0.5 implementation drives ``_-ViewCaptureToFile`` per frame
    /// — true photo-realistic render-engine integration is deferred.
    /// </summary>
    public class RenderQueueHandler : HandlerBase
    {
        private sealed class FrameSpec
        {
            public string OutputPath = "";
            public int Width = 1920;
            public int Height = 1080;
            public string? ViewName;
        }

        private sealed class Job
        {
            public Guid Id = Guid.NewGuid();
            public List<FrameSpec> Frames = new();
            public string Status = "queued"; // queued | running | done | cancelled | error
            public int CompletedFrames;
            public int FailedFrames;
            public string? ErrorMessage;
            public DateTime SubmittedAtUtc = DateTime.UtcNow;
            public DateTime? CompletedAtUtc;
            public CancellationTokenSource Cts = new();
            public List<string> CompletedPaths = new();
        }

        private static readonly ConcurrentDictionary<Guid, Job> _jobs = new();

        public JObject Submit(JObject p)
        {
            var framesTok = p["frames"] as JArray
                ?? throw new System.ArgumentException("'frames' must be a JSON array.");
            if (framesTok.Count == 0)
                throw new System.ArgumentException("'frames' must contain at least one entry.");
            if (framesTok.Count > 1024)
                throw new System.ArgumentException("'frames' max length is 1024.");

            var job = new Job();
            foreach (var frameTok in framesTok)
            {
                var f = frameTok as JObject
                    ?? throw new System.ArgumentException("Each frame must be a JSON object.");
                var path = f["output_path"]?.ToString();
                if (string.IsNullOrWhiteSpace(path) || path.Contains('"'))
                    throw new System.ArgumentException("frame.output_path is required and must not contain quotes.");
                var w = f["width"]?.Value<int>() ?? 1920;
                var h = f["height"]?.Value<int>() ?? 1080;
                if (w <= 0 || h <= 0 || w > 16384 || h > 16384)
                    throw new System.ArgumentException("frame.width/height must be 1..16384.");
                job.Frames.Add(new FrameSpec
                {
                    OutputPath = path,
                    Width = w,
                    Height = h,
                    ViewName = f["view"]?.ToString(),
                });
            }
            _jobs[job.Id] = job;
            EvictExpired();

            // Run the queue on a worker; each frame hops to the UI thread for capture.
            _ = System.Threading.Tasks.Task.Run(() => RunJob(job));

            return new JObject
            {
                ["summary"] = new JObject
                {
                    ["job_id"] = job.Id.ToString(),
                    ["frame_count"] = job.Frames.Count,
                    ["status"] = job.Status,
                },
                ["text"] = $"Submitted render job {job.Id} with {job.Frames.Count} frame(s).",
            };
        }

        public JObject Status(JObject p)
        {
            var jobId = ParseJobId(p);
            if (!_jobs.TryGetValue(jobId, out var job))
                throw new RpcException(RpcErrorCodes.RenderJobUnknown, $"Job {jobId} not found.");
            return JobToJson(job);
        }

        public JObject Cancel(JObject p)
        {
            var jobId = ParseJobId(p);
            if (!_jobs.TryGetValue(jobId, out var job))
                throw new RpcException(RpcErrorCodes.RenderJobUnknown, $"Job {jobId} not found.");
            if (job.Status == "running" || job.Status == "queued")
            {
                job.Cts.Cancel();
                job.Status = "cancelled";
                job.CompletedAtUtc ??= DateTime.UtcNow;
            }
            return JobToJson(job);
        }

        public JObject List(JObject _)
        {
            EvictExpired();
            var rows = new JArray();
            foreach (var job in _jobs.Values.OrderByDescending(j => j.SubmittedAtUtc))
            {
                rows.Add(JobToJson(job));
            }
            return new JObject
            {
                ["summary"] = new JObject { ["count"] = rows.Count },
                ["jobs"] = rows,
            };
        }

        private static Guid ParseJobId(JObject p)
        {
            var raw = p["job_id"]?.ToString();
            if (string.IsNullOrWhiteSpace(raw) || !Guid.TryParse(raw, out var id))
                throw new System.ArgumentException("'job_id' must be a valid GUID string.");
            return id;
        }

        private static JObject JobToJson(Job job)
        {
            return new JObject
            {
                ["job_id"] = job.Id.ToString(),
                ["status"] = job.Status,
                ["frame_count"] = job.Frames.Count,
                ["completed_frames"] = job.CompletedFrames,
                ["failed_frames"] = job.FailedFrames,
                ["completed_paths"] = new JArray(job.CompletedPaths.Cast<object>().ToArray()),
                ["error"] = job.ErrorMessage,
                ["submitted_at_utc"] = job.SubmittedAtUtc.ToString("o"),
                ["completed_at_utc"] = job.CompletedAtUtc?.ToString("o"),
            };
        }

        private static void RunJob(Job job)
        {
            job.Status = "running";
            try
            {
                for (int i = 0; i < job.Frames.Count; i++)
                {
                    if (job.Cts.IsCancellationRequested)
                    {
                        job.Status = "cancelled";
                        return;
                    }
                    var frame = job.Frames[i];
                    var done = new ManualResetEventSlim(false);
                    System.Exception? err = null;
                    RhinoApp.InvokeOnUiThread(new System.Action(() =>
                    {
                        try
                        {
                            // Switch view if requested. ``_-SetView _World _<name>`` is
                            // the canonical scripted form on Rhino 8.
                            if (!string.IsNullOrWhiteSpace(frame.ViewName))
                            {
                                RhinoApp.RunScript($"_-SetView _World _{frame.ViewName}", false);
                            }
                            RhinoApp.RunScript(
                                $"_-ViewCaptureToFile \"{frame.OutputPath}\" _Width={frame.Width} _Height={frame.Height} _Enter",
                                false);
                        }
                        catch (System.Exception ex)
                        {
                            err = ex;
                        }
                        finally
                        {
                            done.Set();
                        }
                    }));
                    if (!done.Wait(System.TimeSpan.FromMinutes(5)))
                    {
                        job.FailedFrames++;
                        job.ErrorMessage = $"frame {i} timed out after 5 minutes";
                        continue;
                    }
                    if (err != null)
                    {
                        job.FailedFrames++;
                        job.ErrorMessage = err.Message;
                    }
                    else
                    {
                        job.CompletedFrames++;
                        job.CompletedPaths.Add(frame.OutputPath);
                    }
                }
                if (job.Status != "cancelled")
                {
                    job.Status = job.FailedFrames > 0 ? "error" : "done";
                }
            }
            catch (System.Exception ex)
            {
                job.Status = "error";
                job.ErrorMessage = ex.Message;
            }
            finally
            {
                job.CompletedAtUtc = DateTime.UtcNow;
            }
        }

        private static void EvictExpired()
        {
            var cutoff = DateTime.UtcNow.AddHours(-1);
            foreach (var pair in _jobs)
            {
                var job = pair.Value;
                if ((job.Status == "done" || job.Status == "cancelled" || job.Status == "error")
                    && job.CompletedAtUtc.HasValue
                    && job.CompletedAtUtc.Value < cutoff)
                {
                    _jobs.TryRemove(pair.Key, out _);
                }
            }
        }
    }
}
