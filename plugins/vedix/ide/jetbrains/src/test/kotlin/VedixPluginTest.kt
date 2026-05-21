// VedixPluginTest.kt — Smoke test for the Vedix JetBrains plugin classes.
//
// We don't spin up the full IntelliJ TestFramework here (that requires a
// downloaded IDE distribution at test time). Instead we just confirm that the
// core plugin classes load via the classloader and that ToolWindowFactory is
// implemented by VedixToolWindowFactory.

import ai.vedix.jetbrains.VedixToolWindowFactory
import ai.vedix.jetbrains.NewManuscriptAction
import ai.vedix.jetbrains.SwitchVenueAction
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.openapi.actionSystem.AnAction
import org.junit.jupiter.api.Assertions.assertNotNull
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class VedixPluginTest {

    @Test
    fun `VedixToolWindowFactory loads and implements ToolWindowFactory`() {
        val cls = Class.forName("ai.vedix.jetbrains.VedixToolWindowFactory")
        assertNotNull(cls, "VedixToolWindowFactory class should load")
        assertTrue(
            ToolWindowFactory::class.java.isAssignableFrom(cls),
            "VedixToolWindowFactory should implement ToolWindowFactory",
        )
        // Confirm we can instantiate it (no-arg constructor required by the platform).
        val instance = VedixToolWindowFactory()
        assertNotNull(instance)
    }

    @Test
    fun `NewManuscriptAction and SwitchVenueAction extend AnAction`() {
        assertTrue(AnAction::class.java.isAssignableFrom(NewManuscriptAction::class.java))
        assertTrue(AnAction::class.java.isAssignableFrom(SwitchVenueAction::class.java))
    }
}
