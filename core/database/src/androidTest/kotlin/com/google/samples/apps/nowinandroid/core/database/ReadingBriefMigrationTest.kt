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

package com.google.samples.apps.nowinandroid.core.database

import android.content.Context
import androidx.room.Room
import androidx.room.testing.MigrationTestHelper
import androidx.sqlite.db.framework.FrameworkSQLiteOpenHelperFactory
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.samples.apps.nowinandroid.core.database.model.ReadingBriefDraftEntity
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import kotlin.test.assertEquals
import kotlin.test.assertNull

@RunWith(AndroidJUnit4::class)
class ReadingBriefMigrationTest {
    @get:Rule
    val migrationHelper = MigrationTestHelper(
        InstrumentationRegistry.getInstrumentation(),
        NiaDatabase::class.java,
        emptyList(),
        FrameworkSQLiteOpenHelperFactory(),
    )

    @Test
    fun migration14To15PreservesNewsAndTopicsAndAddsDraftStorage() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val databaseName = "reading-brief-migration-test"

        migrationHelper.createDatabase(databaseName, 14).apply {
            execSQL(
                """INSERT INTO news_resources
                    (id, title, content, url, header_image_url, publish_date, type)
                    VALUES ('news-1', 'Saved title', 'Body', 'https://example.test/story', NULL, 42, 'Article')""",
            )
            execSQL(
                """INSERT INTO topics
                    (id, name, shortDescription, longDescription, url, imageUrl)
                    VALUES ('topic-1', 'Systems', 'Short', 'Long', 'https://example.test/topic', '')""",
            )
            execSQL(
                "INSERT INTO news_resources_topics (news_resource_id, topic_id) VALUES ('news-1', 'topic-1')",
            )
            close()
        }

        val database = Room.databaseBuilder(context, NiaDatabase::class.java, databaseName).build()
        try {
            val savedNewsAndTopic = database.openHelper.readableDatabase.query(
                """SELECT news_resources.title, topics.name
                    FROM news_resources
                    JOIN news_resources_topics ON news_resources.id = news_resources_topics.news_resource_id
                    JOIN topics ON topics.id = news_resources_topics.topic_id""",
            ).use { cursor ->
                check(cursor.moveToFirst())
                cursor.getString(0) to cursor.getString(1)
            }
            assertEquals("Saved title" to "Systems", savedNewsAndTopic)
            assertNull(database.readingBriefDraftDao().observeDraft().first())

            val draft = ReadingBriefDraftEntity(payload = """{"sources":["SAVED_SELECTION"]}""")
            database.readingBriefDraftDao().saveDraft(draft)
            assertEquals(draft, database.readingBriefDraftDao().observeDraft().first())
        } finally {
            database.close()
        }
        context.deleteDatabase(databaseName)
    }
}
