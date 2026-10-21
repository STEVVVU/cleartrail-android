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

package com.google.samples.apps.nowinandroid.feature.bookmarks.impl

import android.content.ContentResolver
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.google.samples.apps.nowinandroid.core.data.repository.ReadingBriefDraftRepository
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefArticle
import com.google.samples.apps.nowinandroid.core.model.data.ReadingBriefDraft
import com.google.samples.apps.nowinandroid.feature.bookmarks.api.R
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.collect
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import javax.inject.Inject

internal data class ReadingBriefUiState(
    val draft: ReadingBriefDraft = ReadingBriefDraft(),
    val preview: ReadingBriefPreview? = null,
    val destination: Uri? = null,
    val destinationName: String? = null,
    val grant: Long? = null,
    val status: Int? = null,
    val loading: Boolean = true,
)

@HiltViewModel
internal class ReadingBriefViewModel @Inject constructor(
    private val repository: ReadingBriefDraftRepository,
) : ViewModel() {
    private val session = ReadingBriefSession()
    private val draftWriteMutex = Mutex()
    private val mutableState = MutableStateFlow(ReadingBriefUiState())
    val state = mutableState.asStateFlow()

    init {
        viewModelScope.launch {
            repository.observeDraft()
                .catch {
                    mutableState.update { it.copy(loading = false, status = R.string.feature_bookmarks_api_brief_load_failed) }
                }
                .collect { draft ->
                    if (draft != null && mutableState.value.loading) {
                        mutableState.update { it.copy(draft = draft, loading = false) }
                    } else {
                        mutableState.update { it.copy(loading = false) }
                    }
                }
        }
    }

    fun replaceFromSaved(articles: List<ReadingBriefArticle>) {
        updateDraft(mutableState.value.draft.replaceFromSaved(articles))
    }

    fun updateNote(note: String) {
        updateDraft(mutableState.value.draft.copy(privateNote = note.take(4_000)))
    }

    private fun updateDraft(draft: ReadingBriefDraft) {
        viewModelScope.launch {
            session.invalidate()
            mutableState.update {
                it.copy(draft = draft, preview = null, grant = null, status = null)
            }
            runCatching { draftWriteMutex.withLock { repository.saveDraft(draft) } }
                .onFailure {
                    if (it is CancellationException) throw it
                    mutableState.update { it.copy(status = R.string.feature_bookmarks_api_brief_save_failed) }
                }
        }
    }

    fun chooseDestination(uri: Uri?, name: String?) {
        viewModelScope.launch {
            session.invalidate()
            mutableState.update {
                it.copy(
                    destination = uri,
                    destinationName = name,
                    preview = null,
                    grant = null,
                    status = if (uri == null) R.string.feature_bookmarks_api_brief_cancelled else null,
                )
            }
        }
    }

    fun review() {
        viewModelScope.launch {
            session.invalidate()
            runCatching {
                val preview = previewReadingBrief(mutableState.value.draft)
                mutableState.update { it.copy(preview = preview, grant = null, status = null) }
            }.onFailure {
                mutableState.update { it.copy(preview = null, grant = null, status = R.string.feature_bookmarks_api_brief_review_failed) }
            }
        }
    }

    fun approve() {
        viewModelScope.launch {
            val current = mutableState.value
            val preview = current.preview ?: return@launch
            val destination = current.destination ?: return@launch
            val token = session.authorize(preview, destination.toString())
            mutableState.update {
                it.copy(
                    grant = token,
                    status = if (token == null) {
                        R.string.feature_bookmarks_api_brief_invalid
                    } else {
                        R.string.feature_bookmarks_api_brief_approved
                    },
                )
            }
        }
    }

    fun revoke() {
        viewModelScope.launch {
            session.revoke()
            mutableState.update { it.copy(preview = null, grant = null, status = R.string.feature_bookmarks_api_brief_revoked) }
        }
    }

    fun write(resolver: ContentResolver) {
        viewModelScope.launch {
            val current = mutableState.value
            val token = current.grant ?: return@launch
            val preview = current.preview ?: return@launch
            val destination = current.destination ?: return@launch
            mutableState.update { it.copy(grant = null, status = R.string.feature_bookmarks_api_brief_writing) }
            runCatching {
                session.write(token, preview, destination.toString()) { bytes ->
                    withContext(Dispatchers.IO) {
                        val output = resolver.openOutputStream(destination, "wt")
                            ?: error("The selected document cannot be opened.")
                        output.use { stream ->
                            stream.write(bytes)
                            stream.flush()
                        }
                    }
                }
            }.onSuccess { written ->
                mutableState.update {
                    if (written == null) {
                        it.copy(preview = null, grant = null, status = R.string.feature_bookmarks_api_brief_invalid)
                    } else {
                        it.copy(status = R.string.feature_bookmarks_api_brief_success)
                    }
                }
            }.onFailure { error ->
                if (error is CancellationException) throw error
                mutableState.update {
                    it.copy(preview = null, grant = null, status = R.string.feature_bookmarks_api_brief_failed)
                }
            }
        }
    }
}
