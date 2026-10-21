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

package com.google.samples.apps.nowinandroid.core.database.dao

import android.content.Context
import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import com.google.samples.apps.nowinandroid.core.database.NiaDatabase
import com.google.samples.apps.nowinandroid.core.database.model.ReadingBriefDraftEntity
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import org.junit.Test
import kotlin.test.assertEquals

class ReadingBriefDraftDaoTest {
    @Test
    fun draftPersistsAcrossDatabaseReopen() = runBlocking {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val databaseName = "reading-brief-test"
        val draft = ReadingBriefDraftEntity(payload = "{\"sources\":[\"SAVED_SELECTION\"]}")
        Room.databaseBuilder(context, NiaDatabase::class.java, databaseName).build().use { database ->
            database.readingBriefDraftDao().saveDraft(draft)
        }

        Room.databaseBuilder(context, NiaDatabase::class.java, databaseName).build().use { database ->
            assertEquals(draft, database.readingBriefDraftDao().observeDraft().first())
        }
        context.deleteDatabase(databaseName)
    }
}
