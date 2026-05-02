using Newtonsoft.Json.Linq;
using Rhino;

namespace RhinoMCPBridge.Handlers
{
    /// <summary>
    /// Undo / redo operations on the active document.
    /// </summary>
    public class HistoryHandler : HandlerBase
    {
        public JObject Undo(JObject parameters)
        {
            int steps = parameters["steps"]?.Value<int>() ?? 1;
            int undone = 0;

            for (int i = 0; i < steps; i++)
            {
                if (!Doc.Undo())
                    break;
                undone++;
            }

            Doc.Views.Redraw();

            return new JObject
            {
                ["undone_steps"] = undone,
                ["requested_steps"] = steps
            };
        }

        public JObject Redo(JObject parameters)
        {
            int steps = parameters["steps"]?.Value<int>() ?? 1;
            int redone = 0;

            for (int i = 0; i < steps; i++)
            {
                if (!Doc.Redo())
                    break;
                redone++;
            }

            Doc.Views.Redraw();

            return new JObject
            {
                ["redone_steps"] = redone,
                ["requested_steps"] = steps
            };
        }
    }
}
