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

package com.google.samples.apps.nowinandroid.core.data.test.repository

import com.google.samples.apps.nowinandroid.core.data.repository.ReadingBriefDraftRepository
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefDraft
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
internal class FakeReadingBriefDraftRepository @Inject constructor() : ReadingBriefDraftRepository {
    private val draft = MutableStateFlow<ReadingBriefDraft?>(null)

    override fun observeDraft(): Flow<ReadingBriefDraft?> = draft

    override suspend fun saveDraft(draft: ReadingBriefDraft) {
        this.draft.value = draft.copy(articles = draft.articles.toList())
    }
}
