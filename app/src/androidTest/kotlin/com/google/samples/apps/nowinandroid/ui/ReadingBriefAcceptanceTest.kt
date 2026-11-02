/*
 * Copyright 2026 The Android Open Source Project
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

package com.google.samples.apps.nowinandroid.ui

import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performTextReplacement
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import com.google.samples.apps.nowinandroid.MainActivity
import com.google.samples.apps.nowinandroid.core.data.repository.ReadingBriefDraftRepository
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefArticle
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefDraft
import dagger.hilt.android.testing.HiltAndroidRule
import dagger.hilt.android.testing.HiltAndroidTest
import kotlinx.coroutines.runBlocking
import org.junit.Rule
import org.junit.Test
import java.io.FileInputStream
import javax.inject.Inject

@HiltAndroidTest
class ReadingBriefAcceptanceTest {
    @get:Rule(order = 0)
    val hilt = HiltAndroidRule(this)

    @get:Rule(order = 1)
    val compose = createEmptyComposeRule()

    @Inject lateinit var drafts: ReadingBriefDraftRepository

    @Test
    fun reviewInvalidationAndRealDocumentExport() {
        hilt.inject()
        runBlocking {
            drafts.saveDraft(ReadingBriefDraft(listOf(ReadingBriefArticle("synthetic-1", "Synthetic article", "https://example.test/article"))))
        }
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val device = UiDevice.getInstance(instrumentation)
        val evidence = checkNotNull(instrumentation.targetContext.getExternalFilesDir(null))
        val expected = """{"version":1,"sources":["PRIVATE_NOTE","SAVED_SELECTION"],"articles":[{"id":"synthetic-1","title":"Synthetic article","url":"https://example.test/article"}],"privateNote":"Synthetic note"}"""
        ActivityScenario.launch(MainActivity::class.java).use {
            compose.onNodeWithText("Saved").performClick()
            compose.onNodeWithText("Build a reading brief").performClick()
            compose.onNodeWithText("Optional private note").performTextReplacement("Synthetic note")
            compose.onNodeWithText("Choose destination file").performScrollTo().performClick()
            check(device.wait(Until.hasObject(By.pkg("com.android.documentsui")), 15_000))
            check(device.takeScreenshot(evidence.resolve("picker.png")))
            val menu = device.findObject(By.desc("Show roots"))
            menu?.click()
            val downloads = device.wait(Until.findObject(By.text("Downloads")), 10_000)
            checkNotNull(downloads).click()
            checkNotNull(device.wait(Until.findObject(By.res("android", "button1")), 10_000)).click()
            compose.onNodeWithText("Review exact contents").performScrollTo().performClick()
            compose.onNodeWithText(expected).assertExists().performScrollTo()
            check(device.takeScreenshot(evidence.resolve("preview.png")))
            compose.onNodeWithText("Approve these bytes once").performScrollTo().performClick()
            compose.onNodeWithText("Write approved brief").assertExists()
            compose.onNodeWithText("Optional private note").performScrollTo().performTextReplacement("Changed note")
            compose.onNodeWithText("Write approved brief").assertDoesNotExist()
            instrumentation.uiAutomation.executeShellCommand("if [ -f /sdcard/Download/reading-brief.json ]; then wc -c < /sdcard/Download/reading-brief.json; else echo missing; fi").use { descriptor ->
                FileInputStream(descriptor.fileDescriptor).use { input -> check(input.readBytes().decodeToString().trim() == "0") }
            }
            check(device.takeScreenshot(evidence.resolve("invalidated.png")))
            compose.onNodeWithText("Optional private note").performTextReplacement("Synthetic note")
            compose.onNodeWithText("Review exact contents").performScrollTo().performClick()
            compose.onNodeWithText(expected).assertExists()
            compose.onNodeWithText("Approve these bytes once").performScrollTo().performClick()
            compose.onNodeWithText("Write approved brief").performScrollTo().performClick()
            compose.waitUntil(15_000) { compose.onAllNodes(androidx.compose.ui.test.hasText("Reading brief saved.")).fetchSemanticsNodes().isNotEmpty() }
            compose.onNodeWithText("Write approved brief").assertDoesNotExist()
            evidence.resolve("expected.json").writeText(expected)
            check(device.takeScreenshot(evidence.resolve("saved.png")))
        }
    }
}
