// VedixToolWindowFactory.kt — Side-channel tool window for the Vedix plugin.
//
// The tool window is registered in plugin.xml with anchor="right". When the
// platform asks us to populate it (createToolWindowContent), we build a tiny
// vertical panel that explains how to drive the plugin via Tools > Vedix.

package ai.vedix.jetbrains

import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.components.JBLabel
import com.intellij.ui.components.JBPanel
import com.intellij.ui.components.JBScrollPane
import javax.swing.BoxLayout

class VedixToolWindowFactory : ToolWindowFactory {
    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val panel = JBPanel<JBPanel<*>>().apply {
            layout = BoxLayout(this, BoxLayout.Y_AXIS)
        }
        panel.add(JBLabel("Vedix — Research Workbench"))
        panel.add(JBLabel(" "))
        panel.add(JBLabel("Use Tools > Vedix: New Manuscript to start a job."))
        panel.add(JBLabel("Use Tools > Vedix: Switch Venue to re-target an existing job."))
        toolWindow.component.add(JBScrollPane(panel))
    }

    override fun shouldBeAvailable(project: Project): Boolean = true
}
