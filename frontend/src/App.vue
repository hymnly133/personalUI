<template>
	<el-container class="layout-container">
		<el-header class="header">
			<div class="logo">SimpleGraphRAG Visualizer</div>
			<div class="header-stats" v-if="stats">
				<el-tag type="info">Entities: {{ stats.graph?.entities || 0 }}</el-tag>
				<el-tag type="info" class="ml-2"
					>Relationships: {{ stats.graph?.relationships || 0 }}</el-tag
				>
			</div>
		</el-header>

		<el-container class="content-container">
			<el-aside class="aside" :style="{ width: asideWidth + 'px' }">
				<el-tabs v-model="activeTab" class="tabs-container">
					<el-tab-pane label="Search" name="search">
						<div class="tab-pane-content">
							<div class="search-container">
								<h3>
									<el-icon><Search /></el-icon>
									Knowledge Graph Search
								</h3>
								<el-divider />

								<!-- 关键词搜索 -->
								<div class="search-section">
									<h4>Keyword Search</h4>
									<el-input
										v-model="searchKeyword"
										placeholder="Enter keyword to search..."
										clearable
										@keyup.enter="performKeywordSearch"
									>
										<template #prepend>
											<el-icon><Search /></el-icon>
										</template>
									</el-input>

									<div class="search-options mt-2">
										<el-radio-group v-model="searchFuzzy" size="small">
											<el-radio :value="true">Fuzzy Match</el-radio>
											<el-radio :value="false">Exact Match</el-radio>
										</el-radio-group>
										<el-input-number
											v-model="searchLimit"
											:min="1"
											:max="200"
											size="small"
											class="ml-2"
											placeholder="Limit"
											style="width: 100px"
										/>
									</div>

									<el-button
										type="primary"
										class="mt-2 w-full"
										@click="performKeywordSearch"
										:loading="searching"
									>
										<el-icon><Search /></el-icon>
										Search
									</el-button>
								</div>

								<el-divider />

								<!-- 节点查询 -->
								<div class="search-section">
									<h4>Node Detail Query</h4>
									<el-input
										v-model="nodeIdQuery"
										placeholder="Enter node ID (entity name, entity:class, or class name)"
										clearable
										@keyup.enter="performNodeQuery"
									>
										<template #prepend>
											<el-icon><DataAnalysis /></el-icon>
										</template>
									</el-input>
									<el-button
										type="success"
										class="mt-2 w-full"
										@click="performNodeQuery"
										:loading="querying"
									>
										Query Node Details
									</el-button>
								</div>

								<el-divider />

								<!-- 快捷查询 -->
								<div class="search-section">
									<h4>Quick Queries</h4>
									<el-button
										size="small"
										plain
										@click="performEntityGroupQuery"
										:loading="querying"
										class="mb-2"
										style="width: 100%"
									>
										Query Entity Group
									</el-button>
									<el-button
										size="small"
										plain
										@click="performClassGroupQuery"
										:loading="querying"
										style="width: 100%"
									>
										Query Class Group
									</el-button>
									<el-input
										v-model="groupQueryName"
										placeholder="Enter entity/class name"
										size="small"
										class="mt-2"
										clearable
									/>
								</div>

								<el-divider />

								<!-- 搜索结果 -->
								<div class="search-results">
									<div class="result-header">
										<h4>Results</h4>
										<el-button
											v-if="searchResults"
											size="small"
											@click="clearSearchResults"
										>
											Clear
										</el-button>
									</div>

									<div v-if="searchResults" class="result-content">
										<pre class="result-text">{{ searchResults }}</pre>
									</div>

									<el-empty
										v-else
										description="No search results yet"
										:image-size="80"
									/>
								</div>
							</div>
						</div>
					</el-tab-pane>

					<el-tab-pane label="Tasks" name="tasks">
						<div class="tab-pane-content">
							<div class="task-submit">
								<el-input
									v-model="inputText"
									type="textarea"
									:rows="6"
									placeholder="Enter text to extract knowledge..."
								/>
								<el-button
									type="primary"
									class="mt-4 w-full"
									@click="submitTask"
									:loading="submitting"
									size="large"
								>
									Submit Task
								</el-button>
							</div>

							<el-divider>Task History</el-divider>

							<div class="task-list">
								<el-card
									v-for="task in sortedTasks"
									:key="task.task_id"
									class="task-card mb-4"
									shadow="hover"
								>
									<div class="task-header">
										<span class="task-id"
											>Task: {{ task.task_id.substring(0, 8) }}</span
										>
										<el-tag :type="getStatusType(task.status)">{{
											task.status
										}}</el-tag>
									</div>
									<p class="task-text">
										{{ task.input_text.substring(0, 150)
										}}{{ task.input_text.length > 150 ? "..." : "" }}
									</p>

									<!-- 任务进度展示 -->
									<div
										v-if="
											task.status === 'running' ||
											task.status === 'pending' ||
											(progressMap[task.task_id] &&
												progressMap[task.task_id].status === 'running')
										"
										class="mt-2"
									>
										<el-progress
											:percentage="progressMap[task.task_id]?.percentage || 0"
											:status="
												progressMap[task.task_id]?.step === 'failed'
													? 'exception'
													: undefined
											"
										/>
										<div class="progress-details mt-2">
											<div class="progress-msg">
												<el-icon class="is-loading">
													<Loading />
												</el-icon>
												<span>{{
													progressMap[task.task_id]?.message || "Waiting..."
												}}</span>
											</div>
											<div
												class="progress-step"
												v-if="progressMap[task.task_id]?.step"
											>
												Step: {{ formatStep(progressMap[task.task_id]?.step) }}
											</div>
										</div>
									</div>

									<!-- 任务完成信息 -->
									<div
										v-if="task.status === 'completed'"
										class="task-completed mt-2"
									>
										<div class="completed-info">
											<el-tag type="success" size="small">
												<el-icon><SuccessFilled /></el-icon>
												Completed in {{ task.duration?.toFixed(2) || 0 }}s
											</el-tag>
											<el-button
												size="small"
												type="primary"
												plain
												@click="highlightTaskDelta(task.task_id)"
												v-if="taskDeltas[task.task_id]?.has_delta"
											>
												<el-icon><View /></el-icon>
												View Delta
											</el-button>
											<el-button
												size="small"
												type="info"
												plain
												@click="openTaskStagesDialog(task.task_id)"
											>
												<el-icon><InfoFilled /></el-icon>
												View Stages
											</el-button>
										</div>
										<div
											v-if="taskDeltas[task.task_id]?.has_delta"
											class="delta-stats mt-2"
										>
											<el-tag size="small" type="info">
												+{{ taskDeltas[task.task_id].stats.entities }} entities
											</el-tag>
											<el-tag size="small" type="info" class="ml-1">
												+{{ taskDeltas[task.task_id].stats.relationships }}
												relationships
											</el-tag>
										</div>
									</div>

									<!-- 任务失败信息 -->
									<div v-if="task.status === 'failed'" class="task-failed mt-2">
										<el-alert
											type="error"
											:title="task.error || 'Task failed'"
											:closable="false"
											show-icon
										/>
									</div>
								</el-card>
							</div>
						</div>
					</el-tab-pane>

					<el-tab-pane label="Details" name="details">
						<div class="tab-pane-content">
							<!-- 节点详情 -->
							<div v-if="selectedNode && !selectedEdge" class="node-details">
								<h3>
									<el-icon><InfoFilled /></el-icon>
									{{ selectedNode.label }}
								</h3>
								<el-descriptions :column="1" border>
									<el-descriptions-item label="Type">{{
										selectedNode.node_type
									}}</el-descriptions-item>
									<el-descriptions-item label="Classes">
										<el-tag
											v-for="cls in selectedNode.classes"
											:key="cls"
											class="mr-1 mb-1"
											>{{ cls }}</el-tag
										>
									</el-descriptions-item>
									<el-descriptions-item label="Description">{{
										selectedNode.description
									}}</el-descriptions-item>
								</el-descriptions>

								<div v-if="selectedNode.properties" class="mt-4">
									<h4>Properties</h4>
									<div
										v-for="(props, cls) in selectedNode.properties"
										:key="cls"
									>
										<h5 class="cls-title">{{ cls }}</h5>
										<el-descriptions :column="1" size="small" border>
											<el-descriptions-item
												v-for="(val, key) in props"
												:key="key"
												:label="key"
											>
												{{ val }}
											</el-descriptions-item>
										</el-descriptions>
									</div>
								</div>
							</div>

							<!-- 边详情 -->
							<div v-else-if="selectedEdge" class="edge-details">
								<h3>
									<el-icon><Connection /></el-icon>
									Edge Details
								</h3>
								<el-descriptions :column="1" border>
									<el-descriptions-item label="Source">
										<el-tag type="primary">{{
											getNodeLabel(selectedEdge.source)
										}}</el-tag>
									</el-descriptions-item>
									<el-descriptions-item label="Target">
										<el-tag type="success">{{
											getNodeLabel(selectedEdge.target)
										}}</el-tag>
									</el-descriptions-item>
									<el-descriptions-item label="Type">
										<el-tag>{{ selectedEdge.edge_type }}</el-tag>
									</el-descriptions-item>
									<el-descriptions-item
										label="Count"
										v-if="selectedEdge.count !== undefined"
									>
										<el-tag type="warning">{{ selectedEdge.count }}</el-tag>
									</el-descriptions-item>
									<el-descriptions-item label="Description">{{
										selectedEdge.description
									}}</el-descriptions-item>
									<el-descriptions-item
										label="Refer (参与实体)"
										v-if="selectedEdge.refer && selectedEdge.refer.length > 0"
									>
										<el-space wrap>
											<el-tag
												v-for="(ref, idx) in selectedEdge.refer"
												:key="idx"
												type="info"
												size="small"
											>
												{{ ref }}
											</el-tag>
										</el-space>
									</el-descriptions-item>
								</el-descriptions>
							</div>

							<!-- 空状态 -->
							<div v-else class="empty-state">
								<el-empty description="Select a node or edge to view details" />
							</div>
						</div>
					</el-tab-pane>

					<el-tab-pane label="Options" name="options">
						<div class="tab-pane-content">
							<div class="options-container">
								<h3>Display Options</h3>
								<el-divider />

								<div class="option-item">
									<el-switch
										v-model="showClassMasterNodes"
										@change="handleOptionsChange"
										active-text="Show Class Master Nodes"
										inactive-text="Hide Class Master Nodes"
									/>
									<p class="option-desc">
										Toggle visibility of class master nodes and their
										connections
									</p>
								</div>

								<el-divider />

								<div class="option-item">
									<el-switch
										v-model="showCountLabelOnlyAbove1"
										@change="handleOptionsChange"
										active-text="Show Count Only Above 1"
										inactive-text="Show All Counts"
									/>
									<p class="option-desc">
										Only display count labels on edges with count > 1
									</p>
								</div>

								<el-divider />

								<div class="option-item" v-if="selectedTaskId">
									<h4>Current Highlight</h4>
									<p class="option-desc">
										Task: {{ selectedTaskId.substring(0, 8) }}...
									</p>
									<el-button type="danger" size="small" @click="clearHighlight">
										Clear Highlight
									</el-button>
								</div>
							</div>
						</div>
					</el-tab-pane>

					<el-tab-pane label="Increments" name="increments">
						<div class="tab-pane-content">
							<div class="increments-container">
								<h3>Task Incremental Data</h3>
								<el-divider />

								<div
									v-if="Object.keys(taskDeltas).length === 0"
									class="empty-state"
								>
									<el-empty
										description="No completed tasks with delta data yet"
									/>
								</div>

								<div v-else class="delta-list">
									<el-card
										v-for="(delta, taskId) in taskDeltas"
										:key="taskId"
										class="delta-card mb-3"
										:class="{ active: selectedTaskId === taskId }"
										shadow="hover"
									>
										<div class="delta-header">
											<span class="delta-task-id">
												Task: {{ taskId.substring(0, 8) }}
											</span>
											<el-button
												type="primary"
												size="small"
												@click="highlightTaskDelta(taskId)"
											>
												<el-icon><View /></el-icon>
												Highlight
											</el-button>
										</div>

										<div class="delta-content mt-3">
											<el-descriptions :column="1" size="small" border>
												<el-descriptions-item label="Status">
													<el-tag type="success">{{ delta.status }}</el-tag>
												</el-descriptions-item>
												<el-descriptions-item label="Input">
													{{ delta.input_text?.substring(0, 100) }}...
												</el-descriptions-item>
												<el-descriptions-item label="Entities Added">
													<el-tag type="info">{{
														delta.stats.entities
													}}</el-tag>
												</el-descriptions-item>
												<el-descriptions-item label="Relationships Added">
													<el-tag type="info">{{
														delta.stats.relationships
													}}</el-tag>
												</el-descriptions-item>
												<el-descriptions-item label="Classes Added">
													<el-tag type="info">{{ delta.stats.classes }}</el-tag>
												</el-descriptions-item>
											</el-descriptions>

											<el-collapse class="mt-3" accordion>
												<el-collapse-item title="View Entities" name="entities">
													<div
														v-for="entity in delta.delta.entities"
														:key="entity.name"
														class="entity-item"
													>
														<el-tag type="primary">{{ entity.name }}</el-tag>
														<span class="ml-2">{{ entity.description }}</span>
													</div>
												</el-collapse-item>

												<el-collapse-item
													title="View Relationships"
													name="relationships"
												>
													<div
														v-for="(rel, idx) in delta.delta.relationships"
														:key="idx"
														class="relationship-item"
													>
														<div class="relationship-main">
															<el-tag size="small">{{ rel.source }}</el-tag>
															<el-icon class="mx-1"><Right /></el-icon>
															<el-tag size="small">{{ rel.target }}</el-tag>
															<span class="ml-2">{{ rel.description }}</span>
															<el-tag size="small" type="warning" class="ml-2"
																>×{{ rel.count }}</el-tag
															>
														</div>
														<div
															v-if="rel.refer && rel.refer.length > 0"
															class="relationship-refer"
														>
															<span class="refer-label">参与:</span>
															<el-space wrap :size="4">
																<el-tag
																	v-for="(ref, refIdx) in rel.refer"
																	:key="refIdx"
																	type="info"
																	size="small"
																>
																	{{ ref }}
																</el-tag>
															</el-space>
														</div>
													</div>
												</el-collapse-item>
											</el-collapse>
										</div>
									</el-card>
								</div>
							</div>
						</div>
					</el-tab-pane>

					<!-- 数据库管理 -->
					<el-tab-pane label="Database" name="database">
						<div class="tab-pane-content">
							<DatabaseManager @database-loaded="handleDatabaseLoaded" />
						</div>
					</el-tab-pane>
				</el-tabs>
			</el-aside>

			<!-- 可拖拽的分隔线 -->
			<div
				class="resize-handle"
				@mousedown="startResize"
				:class="{ resizing: isResizing }"
			></div>

			<el-main class="main-viz">
				<div id="graph-container" ref="graphContainer"></div>
				<div class="viz-controls">
					<el-button-group>
						<el-button type="primary" @click="refreshGraph"
							>Refresh Graph</el-button
						>
						<el-button @click="resetZoom">Reset Zoom</el-button>
						<el-button
							v-if="selectedTaskId"
							type="danger"
							@click="clearHighlight"
						>
							Clear Highlight
						</el-button>
					</el-button-group>
				</div>
			</el-main>
		</el-container>

		<!-- 任务阶段详情对话框 -->
		<el-dialog
			v-model="stagesDialogVisible"
			title="Task Stages Details"
			width="80%"
			:close-on-click-modal="false"
			destroy-on-close
		>
			<div v-if="currentStageDetails" class="stages-dialog">
				<el-descriptions :column="2" border class="mb-4">
					<el-descriptions-item label="Task ID">
						{{ currentStageDetails.task_id.substring(0, 16) }}...
					</el-descriptions-item>
					<el-descriptions-item label="Status">
						<el-tag :type="getStatusType(currentStageDetails.status)">
							{{ currentStageDetails.status }}
						</el-tag>
					</el-descriptions-item>
					<el-descriptions-item label="Duration" :span="2">
						{{ currentStageDetails.duration?.toFixed(2) || 0 }}s
					</el-descriptions-item>
					<el-descriptions-item label="Input Text" :span="2">
						{{ currentStageDetails.input_text }}
					</el-descriptions-item>
				</el-descriptions>

				<el-divider>Processing Stages</el-divider>

				<el-collapse accordion>
					<!-- System Update 阶段 -->
					<el-collapse-item
						v-if="currentStageDetails.stages?.system_update"
						name="system_update"
					>
						<template #title>
							<div class="stage-title">
								<el-tag type="primary">System Update</el-tag>
								<span class="ml-2">
									{{
										currentStageDetails.stages.system_update.timestamp
											? new Date(
													currentStageDetails.stages.system_update.timestamp
											  ).toLocaleString()
											: ""
									}}
								</span>
							</div>
						</template>

						<div class="stage-content">
							<!-- 输入数据 -->
							<el-card class="mb-3" shadow="never">
								<template #header>
									<div class="card-header">
										<span
											><el-icon><Right /></el-icon> Input Data</span
										>
									</div>
								</template>
								<el-descriptions :column="1" size="small" border>
									<el-descriptions-item label="Input Text">
										{{
											currentStageDetails.stages.system_update.input?.input_text
										}}
									</el-descriptions-item>
									<el-descriptions-item label="Existing Classes">
										<el-tag
											v-for="cls in currentStageDetails.stages.system_update
												.input?.existing_classes"
											:key="cls"
											size="small"
											class="mr-1"
										>
											{{ cls }}
										</el-tag>
									</el-descriptions-item>
									<el-descriptions-item label="Classes Count">
										{{
											currentStageDetails.stages.system_update.input
												?.classes_count
										}}
									</el-descriptions-item>
								</el-descriptions>
							</el-card>

							<!-- 输出数据 -->
							<el-card class="mb-3" shadow="never">
								<template #header>
									<div class="card-header">
										<span
											><el-icon><Right /></el-icon> Output Data</span
										>
									</div>
								</template>
								<el-descriptions :column="1" size="small" border>
									<el-descriptions-item label="Update Needed">
										<el-tag
											:type="
												currentStageDetails.stages.system_update.output?.needed
													? 'success'
													: 'info'
											"
										>
											{{
												currentStageDetails.stages.system_update.output?.needed
													? "Yes"
													: "No"
											}}
										</el-tag>
									</el-descriptions-item>
									<el-descriptions-item
										label="Added Classes"
										v-if="
											currentStageDetails.stages.system_update.output
												?.added_classes?.length
										"
									>
										<el-tag
											v-for="cls in currentStageDetails.stages.system_update
												.output?.added_classes"
											:key="cls"
											type="success"
											size="small"
											class="mr-1"
										>
											{{ cls }}
										</el-tag>
									</el-descriptions-item>
									<el-descriptions-item
										label="Enhanced Classes"
										v-if="
											currentStageDetails.stages.system_update.output
												?.enhanced_classes?.length
										"
									>
										<el-tag
											v-for="cls in currentStageDetails.stages.system_update
												.output?.enhanced_classes"
											:key="cls"
											type="warning"
											size="small"
											class="mr-1"
										>
											{{ cls }}
										</el-tag>
									</el-descriptions-item>
									<el-descriptions-item label="Total Classes in System">
										{{
											currentStageDetails.stages.system_update.output
												?.total_classes_in_system
										}}
									</el-descriptions-item>
								</el-descriptions>
							</el-card>

							<!-- LLM 响应 -->
							<el-card
								v-if="currentStageDetails.stages.system_update.llm_response"
								shadow="never"
							>
								<template #header>
									<div class="card-header">
										<span
											><el-icon><Right /></el-icon> LLM Response</span
										>
									</div>
								</template>
								<pre class="llm-response">{{
									currentStageDetails.stages.system_update.llm_response
								}}</pre>
							</el-card>
						</div>
					</el-collapse-item>

					<!-- Extraction 阶段 -->
					<el-collapse-item
						v-if="currentStageDetails.stages?.extraction"
						name="extraction"
					>
						<template #title>
							<div class="stage-title">
								<el-tag type="success">Extraction</el-tag>
								<span class="ml-2">
									{{
										currentStageDetails.stages.extraction.timestamp
											? new Date(
													currentStageDetails.stages.extraction.timestamp
											  ).toLocaleString()
											: ""
									}}
								</span>
							</div>
						</template>

						<div class="stage-content">
							<!-- 输入数据 -->
							<el-card class="mb-3" shadow="never">
								<template #header>
									<div class="card-header">
										<span
											><el-icon><Right /></el-icon> Input Data</span
										>
									</div>
								</template>
								<el-descriptions :column="1" size="small" border>
									<el-descriptions-item label="Input Text">
										{{
											currentStageDetails.stages.extraction.input?.input_text
										}}
									</el-descriptions-item>
									<el-descriptions-item label="Available Classes">
										<el-tag
											v-for="cls in currentStageDetails.stages.extraction.input
												?.available_classes"
											:key="cls"
											size="small"
											class="mr-1"
										>
											{{ cls }}
										</el-tag>
									</el-descriptions-item>
								</el-descriptions>
							</el-card>

							<!-- 输出数据 -->
							<el-card class="mb-3" shadow="never">
								<template #header>
									<div class="card-header">
										<span
											><el-icon><Right /></el-icon> Output Data</span
										>
									</div>
								</template>
								<el-descriptions :column="1" size="small" border class="mb-3">
									<el-descriptions-item label="Entities Count">
										<el-tag type="success">
											{{
												currentStageDetails.stages.extraction.output
													?.entities_count
											}}
										</el-tag>
									</el-descriptions-item>
									<el-descriptions-item label="Relationships Count">
										<el-tag type="info">
											{{
												currentStageDetails.stages.extraction.output
													?.relationships_count
											}}
										</el-tag>
									</el-descriptions-item>
								</el-descriptions>

								<!-- 实体列表 -->
								<el-divider content-position="left"
									>Extracted Entities</el-divider
								>
								<div class="entities-list">
									<el-card
										v-for="entity in currentStageDetails.stages.extraction
											.output?.entities"
										:key="entity.name"
										class="mb-2"
										shadow="hover"
									>
										<div class="entity-header">
											<el-tag type="primary">{{ entity.name }}</el-tag>
											<el-tag
												v-for="cls in entity.classes"
												:key="cls"
												size="small"
												class="ml-1"
											>
												{{ cls }}
											</el-tag>
										</div>
										<div class="entity-desc mt-2">{{ entity.description }}</div>
										<div
											v-if="
												entity.properties &&
												Object.keys(entity.properties).length > 0
											"
											class="entity-props mt-2"
										>
											<el-descriptions :column="1" size="small" border>
												<template
													v-for="(props, className) in entity.properties"
													:key="className"
												>
													<el-descriptions-item
														:label="`${className}.${propName}`"
														v-for="(propValue, propName) in props"
														:key="propName"
													>
														{{ propValue }}
													</el-descriptions-item>
												</template>
											</el-descriptions>
										</div>
									</el-card>
								</div>

								<!-- 关系列表 -->
								<el-divider content-position="left"
									>Extracted Relationships</el-divider
								>
								<div class="relationships-list">
									<div
										v-for="(rel, idx) in currentStageDetails.stages.extraction
											.output?.relationships"
										:key="idx"
										class="relationship-item mb-2"
									>
										<div class="relationship-main">
											<el-tag size="small">{{ rel.source }}</el-tag>
											<el-icon class="mx-1"><Right /></el-icon>
											<el-tag size="small">{{ rel.target }}</el-tag>
											<span class="ml-2">{{ rel.description }}</span>
											<el-tag size="small" type="warning" class="ml-2"
												>×{{ rel.count }}</el-tag
											>
										</div>
									</div>
								</div>
							</el-card>

							<!-- LLM 响应 -->
							<el-card
								v-if="currentStageDetails.stages.extraction.llm_response"
								shadow="never"
							>
								<template #header>
									<div class="card-header">
										<span
											><el-icon><Right /></el-icon> LLM Response</span
										>
									</div>
								</template>
								<pre class="llm-response">{{
									currentStageDetails.stages.extraction.llm_response
								}}</pre>
							</el-card>
						</div>
					</el-collapse-item>

					<!-- Merging 阶段 -->
					<el-collapse-item
						v-if="currentStageDetails.stages?.merging"
						name="merging"
					>
						<template #title>
							<div class="stage-title">
								<el-tag type="warning">Merging</el-tag>
								<span class="ml-2">
									{{
										currentStageDetails.stages.merging.timestamp
											? new Date(
													currentStageDetails.stages.merging.timestamp
											  ).toLocaleString()
											: ""
									}}
								</span>
							</div>
						</template>

						<div class="stage-content">
							<!-- 输入数据 -->
							<el-card class="mb-3" shadow="never">
								<template #header>
									<div class="card-header">
										<span
											><el-icon><Right /></el-icon> Input Data</span
										>
									</div>
								</template>
								<el-descriptions :column="1" size="small" border class="mb-3">
									<el-descriptions-item label="Delta Summary">
										{{
											currentStageDetails.stages.merging.input?.delta_summary
										}}
									</el-descriptions-item>
									<el-descriptions-item label="Smart Merge Enabled">
										<el-tag
											:type="
												currentStageDetails.stages.merging.input
													?.enable_smart_merge
													? 'success'
													: 'info'
											"
										>
											{{
												currentStageDetails.stages.merging.input
													?.enable_smart_merge
													? "Yes"
													: "No"
											}}
										</el-tag>
									</el-descriptions-item>
									<el-descriptions-item label="Before Merge State">
										<el-space direction="vertical" :size="4">
											<span>
												System Classes:
												{{
													currentStageDetails.stages.merging.input
														?.current_state?.system_classes || 0
												}}
											</span>
											<span>
												Graph Entities:
												{{
													currentStageDetails.stages.merging.input
														?.current_state?.graph_entities || 0
												}}
											</span>
											<span>
												Graph Relationships:
												{{
													currentStageDetails.stages.merging.input
														?.current_state?.graph_relationships || 0
												}}
											</span>
										</el-space>
									</el-descriptions-item>
								</el-descriptions>

								<!-- 待合并的实体列表 -->
								<el-divider content-position="left"
									>Entities to Merge</el-divider
								>
								<div class="entities-list">
									<el-card
										v-for="entity in currentStageDetails.stages.merging.input
											?.delta_to_merge?.entities"
										:key="entity.name"
										class="mb-2"
										shadow="hover"
									>
										<div class="entity-header">
											<el-tag type="primary">{{ entity.name }}</el-tag>
											<el-tag
												v-for="cls in entity.classes"
												:key="cls"
												size="small"
												class="ml-1"
											>
												{{ cls }}
											</el-tag>
										</div>
										<div class="entity-desc mt-2">{{ entity.description }}</div>
										<div
											v-if="
												entity.properties &&
												Object.keys(entity.properties).length > 0
											"
											class="entity-props mt-2"
										>
											<el-descriptions :column="1" size="small" border>
												<template
													v-for="(props, className) in entity.properties"
													:key="className"
												>
													<el-descriptions-item
														:label="`${className}.${propName}`"
														v-for="(propValue, propName) in props"
														:key="propName"
													>
														{{ propValue }}
													</el-descriptions-item>
												</template>
											</el-descriptions>
										</div>
									</el-card>
								</div>

								<!-- 待合并的关系列表 -->
								<el-divider content-position="left"
									>Relationships to Merge</el-divider
								>
								<div class="relationships-list">
									<div
										v-for="(rel, idx) in currentStageDetails.stages.merging
											.input?.delta_to_merge?.relationships"
										:key="idx"
										class="relationship-item mb-2"
									>
										<div class="relationship-main">
											<el-tag size="small">{{ rel.source }}</el-tag>
											<el-icon class="mx-1"><Right /></el-icon>
											<el-tag size="small">{{ rel.target }}</el-tag>
											<span class="ml-2">{{ rel.description }}</span>
											<el-tag size="small" type="warning" class="ml-2"
												>×{{ rel.count }}</el-tag
											>
										</div>
									</div>
								</div>
							</el-card>

							<!-- 输出数据 -->
							<el-card class="mb-3" shadow="never">
								<template #header>
									<div class="card-header">
										<span
											><el-icon><Right /></el-icon> Output Data</span
										>
									</div>
								</template>
								<el-descriptions :column="1" size="small" border class="mb-3">
									<el-descriptions-item label="Merge Summary">
										{{
											currentStageDetails.stages.merging.output?.merge_summary
										}}
									</el-descriptions-item>
									<el-descriptions-item
										label="Merge Notes"
										v-if="
											currentStageDetails.stages.merging.output?.merge_notes
										"
									>
										{{ currentStageDetails.stages.merging.output?.merge_notes }}
									</el-descriptions-item>
									<el-descriptions-item label="Merge Statistics">
										<el-space wrap>
											<el-tag type="info" size="small">
												Duplicates:
												{{
													currentStageDetails.stages.merging.output
														?.merge_statistics?.duplicates_found || 0
												}}
											</el-tag>
											<el-tag type="warning" size="small">
												Conflicts:
												{{
													currentStageDetails.stages.merging.output
														?.merge_statistics?.conflicts_resolved || 0
												}}
											</el-tag>
											<el-tag type="success" size="small">
												Aligned:
												{{
													currentStageDetails.stages.merging.output
														?.merge_statistics?.names_aligned || 0
												}}
											</el-tag>
											<el-tag type="primary" size="small">
												Optimized:
												{{
													currentStageDetails.stages.merging.output
														?.merge_statistics?.descriptions_optimized || 0
												}}
											</el-tag>
										</el-space>
									</el-descriptions-item>
									<el-descriptions-item label="Apply Statistics">
										<el-space direction="vertical" :size="4">
											<span>
												Entities Added:
												{{
													currentStageDetails.stages.merging.output
														?.apply_statistics?.entities_added || 0
												}}, Updated:
												{{
													currentStageDetails.stages.merging.output
														?.apply_statistics?.entities_updated || 0
												}}
											</span>
											<span>
												Relationships Added:
												{{
													currentStageDetails.stages.merging.output
														?.apply_statistics?.relationships_added || 0
												}}, Updated:
												{{
													currentStageDetails.stages.merging.output
														?.apply_statistics?.relationships_updated || 0
												}}
											</span>
										</el-space>
									</el-descriptions-item>
									<el-descriptions-item label="After Merge State">
										<el-space direction="vertical" :size="4">
											<span>
												System Classes:
												{{
													currentStageDetails.stages.merging.output?.final_state
														?.system_classes || 0
												}}
											</span>
											<span>
												Graph Entities:
												{{
													currentStageDetails.stages.merging.output?.final_state
														?.graph_entities || 0
												}}
											</span>
											<span>
												Graph Relationships:
												{{
													currentStageDetails.stages.merging.output?.final_state
														?.graph_relationships || 0
												}}
											</span>
										</el-space>
									</el-descriptions-item>
								</el-descriptions>

								<!-- 优化后的实体列表 -->
								<el-divider content-position="left"
									>Optimized Entities</el-divider
								>
								<div class="entities-list">
									<el-card
										v-for="entity in currentStageDetails.stages.merging.output
											?.optimized_delta?.entities"
										:key="entity.name"
										class="mb-2"
										shadow="hover"
									>
										<div class="entity-header">
											<el-tag type="success">{{ entity.name }}</el-tag>
											<el-tag
												v-for="cls in entity.classes"
												:key="cls"
												size="small"
												class="ml-1"
											>
												{{ cls }}
											</el-tag>
										</div>
										<div class="entity-desc mt-2">{{ entity.description }}</div>
										<div
											v-if="
												entity.properties &&
												Object.keys(entity.properties).length > 0
											"
											class="entity-props mt-2"
										>
											<el-descriptions :column="1" size="small" border>
												<template
													v-for="(props, className) in entity.properties"
													:key="className"
												>
													<el-descriptions-item
														:label="`${className}.${propName}`"
														v-for="(propValue, propName) in props"
														:key="propName"
													>
														{{ propValue }}
													</el-descriptions-item>
												</template>
											</el-descriptions>
										</div>
									</el-card>
								</div>

								<!-- 优化后的关系列表 -->
								<el-divider content-position="left"
									>Optimized Relationships</el-divider
								>
								<div class="relationships-list">
									<div
										v-for="(rel, idx) in currentStageDetails.stages.merging
											.output?.optimized_delta?.relationships"
										:key="idx"
										class="relationship-item mb-2"
									>
										<div class="relationship-main">
											<el-tag size="small">{{ rel.source }}</el-tag>
											<el-icon class="mx-1"><Right /></el-icon>
											<el-tag size="small">{{ rel.target }}</el-tag>
											<span class="ml-2">{{ rel.description }}</span>
											<el-tag size="small" type="warning" class="ml-2"
												>×{{ rel.count }}</el-tag
											>
										</div>
									</div>
								</div>
							</el-card>

							<!-- LLM 响应 -->
							<el-card
								v-if="currentStageDetails.stages.merging.llm_response"
								shadow="never"
							>
								<template #header>
									<div class="card-header">
										<span
											><el-icon><Right /></el-icon> LLM Response</span
										>
									</div>
								</template>
								<pre class="llm-response">{{
									currentStageDetails.stages.merging.llm_response
								}}</pre>
							</el-card>
						</div>
					</el-collapse-item>
				</el-collapse>
			</div>

			<div v-else class="loading-container">
				<el-icon class="is-loading" :size="32"><Loading /></el-icon>
				<p>Loading stage details...</p>
			</div>
		</el-dialog>
	</el-container>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from "vue";
import axios from "axios";
import * as d3 from "d3";
import { ElMessage } from "element-plus";
import {
	Loading,
	SuccessFilled,
	InfoFilled,
	Connection,
	View,
	Right,
	Search,
	DataAnalysis,
} from "@element-plus/icons-vue";
import DatabaseManager from "./components/DatabaseManager.vue";

interface Node extends d3.SimulationNodeDatum {
	id: string;
	label: string;
	group: number;
	size: number;
	description: string;
	node_type: string;
	classes: string[];
	properties?: Record<string, Record<string, string>>;
}

interface Link extends d3.SimulationLinkDatum<Node> {
	source: string | Node;
	target: string | Node;
	value: number;
	description: string;
	edge_type: string;
	count?: number;
	refer?: string[]; // 参与此关系的其他实体
	linkIndex?: number; // 在相同source-target对中的索引
	linkTotal?: number; // 相同source-target对的总数
}

const activeTab = ref("tasks");
const inputText = ref("");
const submitting = ref(false);
const tasks = ref<any[]>([]);
const stats = ref<any>(null);
const progressMap = ref<Record<string, any>>({});
const selectedNode = ref<Node | null>(null);
const selectedEdge = ref<Link | null>(null);
const graphContainer = ref<HTMLElement | null>(null);

// 显示选项
const showClassMasterNodes = ref(false);
const showCountLabelOnlyAbove1 = ref(true);

// 增量数据相关
const taskDeltas = ref<Record<string, any>>({});
const selectedTaskId = ref<string | null>(null);
const highlightedNodeIds = ref<Set<string>>(new Set());
const highlightedEdgeIds = ref<Set<string>>(new Set());

// 任务阶段详情相关
const stagesDialogVisible = ref(false);
const currentStageDetails = ref<any>(null);

// 搜索相关
const searchKeyword = ref("");
const searchFuzzy = ref(true);
const searchLimit = ref(50);
const searching = ref(false);
const nodeIdQuery = ref("");
const querying = ref(false);
const groupQueryName = ref("");
const searchResults = ref<string | null>(null);

// 左侧面板宽度调整相关
const asideWidth = ref(600); // 默认宽度 600px
const isResizing = ref(false);
const minAsideWidth = 300; // 最小宽度
const maxAsideWidth = 1200; // 最大宽度

// 图谱渲染相关变量
let svg: d3.Selection<SVGSVGElement, unknown, null, undefined>;
let container: d3.Selection<SVGGElement, unknown, null, undefined>;
let linkGroup: d3.Selection<SVGGElement, unknown, null, undefined>;
let nodeGroup: d3.Selection<SVGGElement, unknown, null, undefined>;
let simulation: d3.Simulation<Node, Link>;
let zoom: d3.ZoomBehavior<SVGSVGElement, unknown>;

// 颜色比例尺（全局唯一，确保相同group始终相同颜色）
const colorScale = d3.scaleOrdinal(d3.schemeSet3.concat(d3.schemeCategory10));

// 图谱数据缓存（用于增量更新）
const graphData = ref<{ nodes: Node[]; links: Link[] }>({
	nodes: [],
	links: [],
});
const isGraphInitialized = ref(false);

const sortedTasks = computed(() => {
	return [...tasks.value].sort((a, b) => {
		return (
			new Date(b.created_at || 0).getTime() -
			new Date(a.created_at || 0).getTime()
		);
	});
});

const getStatusType = (status: string) => {
	const types: Record<string, string> = {
		pending: "info",
		running: "warning",
		completed: "success",
		failed: "danger",
		cancelled: "info",
	};
	return types[status] || "info";
};

const formatStep = (step: string) => {
	const stepLabels: Record<string, string> = {
		submitted: "Submitted",
		started: "Started",
		extracting_entities: "Extracting Entities",
		extracting_relationships: "Extracting Relationships",
		merging: "Merging Data",
		building_graph: "Building Graph",
		completed: "Completed",
		failed: "Failed",
	};
	return stepLabels[step] || step;
};

const getNodeLabel = (nodeOrId: string | Node) => {
	if (typeof nodeOrId === "string") {
		return nodeOrId;
	}
	return nodeOrId.label || nodeOrId.id;
};

const handleOptionsChange = () => {
	// 选项改变时，使用增量更新而非完全刷新
	if (isGraphInitialized.value && graphData.value) {
		const { filteredNodes, filteredLinks } = filterGraphData(graphData.value);

		// 更新力导向模拟
		simulation.nodes(filteredNodes);
		const linkForce = simulation.force("link") as d3.ForceLink<Node, Link>;
		if (linkForce) {
			linkForce.links(filteredLinks);
		}

		// 更新渲染
		updateLinks(filteredLinks);
		updateNodes(filteredNodes);

		// 温和重启
		simulation.alpha(0.3).restart();
	}
};

const fetchTaskDelta = async (taskId: string) => {
	try {
		const res = await axios.get(`/api/tasks/${taskId}/delta`);
		if (res.data.has_delta) {
			taskDeltas.value[taskId] = res.data;
			return res.data;
		}
	} catch (err) {
		console.error(`Failed to fetch delta for task ${taskId}`, err);
	}
	return null;
};

const openTaskStagesDialog = async (taskId: string) => {
	stagesDialogVisible.value = true;
	currentStageDetails.value = null;

	try {
		const res = await axios.get(`/api/tasks/${taskId}/stages`);
		currentStageDetails.value = res.data;
	} catch (err) {
		console.error(`Failed to fetch stages for task ${taskId}`, err);
		ElMessage.error("Failed to load task stages details");
		stagesDialogVisible.value = false;
	}
};

const highlightTaskDelta = (taskId: string) => {
	const delta = taskDeltas.value[taskId];
	if (!delta || !delta.has_delta) {
		ElMessage.warning("No delta data available for this task");
		return;
	}

	selectedTaskId.value = taskId;

	// 清空之前的高亮
	highlightedNodeIds.value.clear();
	highlightedEdgeIds.value.clear();

	// 收集增量数据中的节点和边
	const deltaData = delta.delta;

	// 添加实体节点
	if (deltaData.entities) {
		deltaData.entities.forEach((entity: any) => {
			highlightedNodeIds.value.add(entity.name);
			// 同时添加类节点
			if (entity.classes) {
				entity.classes.forEach((cls: any) => {
					const classNodeId = `${entity.name}:${cls.name}`;
					highlightedNodeIds.value.add(classNodeId);
				});
			}
		});
	}

	// 添加关系边
	if (deltaData.relationships) {
		deltaData.relationships.forEach((rel: any) => {
			const edgeId = `${rel.source}-${rel.target}`;
			highlightedEdgeIds.value.add(edgeId);
		});
	}

	// 只更新样式，不重新渲染整个图表
	updateGraphStyles();

	ElMessage.success({
		message: `Highlighting ${highlightedNodeIds.value.size} nodes and ${highlightedEdgeIds.value.size} edges from task`,
		duration: 3000,
	});
};

const clearHighlight = () => {
	selectedTaskId.value = null;
	highlightedNodeIds.value.clear();
	highlightedEdgeIds.value.clear();
	// 只需要重新渲染样式，不需要完全刷新
	updateGraphStyles();
};

const filterGraphData = (data: { nodes: Node[]; links: Link[] }) => {
	let filteredNodes = [...data.nodes];
	let filteredLinks = [...data.links];

	if (!showClassMasterNodes.value) {
		// 过滤掉类主节点
		const classMasterIds = new Set(
			data.nodes.filter((n) => n.node_type === "class_master").map((n) => n.id)
		);
		filteredNodes = filteredNodes.filter((n) => n.node_type !== "class_master");
		// 过滤掉与类主节点相关的边
		filteredLinks = filteredLinks.filter(
			(l) =>
				!classMasterIds.has(
					typeof l.source === "string" ? l.source : l.source.id
				) &&
				!classMasterIds.has(
					typeof l.target === "string" ? l.target : l.target.id
				)
		);
	}

	return { filteredNodes, filteredLinks };
};

const incrementalUpdateGraph = (newData: { nodes: Node[]; links: Link[] }) => {
	if (!simulation || !linkGroup || !nodeGroup) {
		// 如果还没初始化，直接初始化
		initGraph(newData);
		return;
	}

	// 保存旧数据用于对比
	const oldNodeIds = new Set(graphData.value.nodes.map((n) => n.id));

	// 更新缓存数据
	graphData.value = { nodes: [...newData.nodes], links: [...newData.links] };

	// 过滤数据
	const { filteredNodes, filteredLinks } = filterGraphData(newData);

	// 找出新增的节点和边
	const newNodes = filteredNodes.filter((n) => !oldNodeIds.has(n.id));
	const newNodeIds = new Set(filteredNodes.map((n) => n.id));

	// 找出需要删除的节点
	const nodesToRemove = simulation.nodes().filter((n) => !newNodeIds.has(n.id));

	console.log(
		`Graph update: +${newNodes.length} nodes, -${nodesToRemove.length} nodes`
	);

	// 更新力导向模拟的节点数据
	simulation.nodes(filteredNodes);

	// 更新力导向模拟的边数据
	const linkForce = simulation.force("link") as d3.ForceLink<Node, Link>;
	if (linkForce) {
		linkForce.links(filteredLinks);
	}

	// 更新边的渲染
	updateLinks(filteredLinks);

	// 更新节点的渲染
	updateNodes(filteredNodes);

	// 重启模拟（温和重启）
	simulation.alpha(0.3).restart();
};

const updateGraphStyles = () => {
	// 只更新样式，不改变数据和位置
	if (!nodeGroup || !linkGroup) return;

	// 更新节点样式
	nodeGroup.selectAll("g").each(function (d: any) {
		const node = d3.select(this);
		const isHighlighted = highlightedNodeIds.value.has(d.id);

		node
			.select("path")
			.attr("fill", isHighlighted ? "#ff6b6b" : colorScale(d.group.toString()))
			.attr("stroke", isHighlighted ? "#ff0000" : "#fff")
			.attr("stroke-width", isHighlighted ? 3 : 1.5)
			.attr(
				"d",
				d3
					.symbol()
					.type(() => {
						if (d.node_type === "class_master") return d3.symbolSquare;
						if (d.node_type === "class_node") return d3.symbolTriangle;
						return d3.symbolCircle;
					})
					.size(() => {
						const baseSize = d.size * d.size * 5;
						return isHighlighted ? baseSize * 2 : baseSize;
					})
			);
	});

	// 更新边样式
	linkGroup.selectAll("g").each(function (d: any) {
		const link = d3.select(this);
		const sourceId = typeof d.source === "string" ? d.source : d.source.id;
		const targetId = typeof d.target === "string" ? d.target : d.target.id;
		const edgeId = `${sourceId}-${targetId}`;
		const isHighlighted = highlightedEdgeIds.value.has(edgeId);

		link
			.select(".link-line")
			.attr("stroke", isHighlighted ? "#ff6b6b" : "#999")
			.attr("stroke-opacity", isHighlighted ? 1 : 0.6)
			.attr("stroke-width", () => {
				const baseWidth = Math.sqrt(d.value || 1) + 1;
				return isHighlighted ? baseWidth + 2 : baseWidth;
			});
	});
};

const updateLinks = (linksData: Link[]) => {
	if (!linkGroup) return;

	// 为每条边计算索引（在相同source-target对中的位置）
	const linksByPair = new Map<string, Link[]>();
	linksData.forEach((link) => {
		const sourceId =
			typeof link.source === "string" ? link.source : link.source.id;
		const targetId =
			typeof link.target === "string" ? link.target : link.target.id;
		const pairKey = `${sourceId}-${targetId}`;
		if (!linksByPair.has(pairKey)) {
			linksByPair.set(pairKey, []);
		}
		linksByPair.get(pairKey)!.push(link);
	});

	// 为每条边添加linkIndex和linkTotal属性
	const linksWithIndex = linksData.map((link) => {
		const sourceId =
			typeof link.source === "string" ? link.source : link.source.id;
		const targetId =
			typeof link.target === "string" ? link.target : link.target.id;
		const pairKey = `${sourceId}-${targetId}`;
		const linksInPair = linksByPair.get(pairKey)!;
		const linkIndex = linksInPair.indexOf(link);
		return {
			...link,
			linkIndex,
			linkTotal: linksInPair.length,
		};
	});

	// D3 data join
	// 使用 source + target + description + refer 作为唯一标识，支持多条关系
	const linkSelection = linkGroup
		.selectAll<SVGGElement, Link>(".link-group")
		.data(linksWithIndex, (d: any) => {
			const sourceId = typeof d.source === "string" ? d.source : d.source.id;
			const targetId = typeof d.target === "string" ? d.target : d.target.id;
			const desc = d.description || "";
			const refer = d.refer ? d.refer.sort().join(",") : "";
			return `${sourceId}-${targetId}-${desc}-${refer}`;
		});

	// EXIT: 移除不再存在的边
	linkSelection.exit().remove();

	// ENTER: 添加新边
	const linkEnter = linkSelection
		.enter()
		.append("g")
		.attr("class", "link-group")
		.attr("cursor", "pointer")
		.on("click", function (event, d) {
			event.stopPropagation();
			selectedEdge.value = d;
			selectedNode.value = null;
			activeTab.value = "details";
			// 高亮选中的边
			d3.selectAll(".link-line")
				.attr("stroke", "#999")
				.attr("stroke-width", (ld: any) => Math.sqrt(ld.value || 1) + 1);
			d3.select(this)
				.select(".link-line")
				.attr("stroke", "#409eff")
				.attr("stroke-width", (ld: any) => Math.sqrt(ld.value || 1) + 3);
		})
		.on("mouseenter", function (event, d: any) {
			const sourceId = typeof d.source === "string" ? d.source : d.source.id;
			const targetId = typeof d.target === "string" ? d.target : d.target.id;
			const edgeId = `${sourceId}-${targetId}`;
			const isHighlighted = highlightedEdgeIds.value.has(edgeId);

			d3.select(this)
				.select(".link-line")
				.attr("stroke", isHighlighted ? "#ff6b6b" : "#67c23a")
				.attr("stroke-width", (ld: any) => Math.sqrt(ld.value || 1) + 4)
				.attr("stroke-opacity", 1);
		})
		.on("mouseleave", function (event, d: any) {
			const sourceId = typeof d.source === "string" ? d.source : d.source.id;
			const targetId = typeof d.target === "string" ? d.target : d.target.id;
			const edgeId = `${sourceId}-${targetId}`;
			const isHighlighted = highlightedEdgeIds.value.has(edgeId);

			d3.select(this)
				.select(".link-line")
				.attr("stroke", isHighlighted ? "#ff6b6b" : "#999")
				.attr("stroke-width", (ld: any) => {
					const baseWidth = Math.sqrt(ld.value || 1) + 1;
					return isHighlighted ? baseWidth + 2 : baseWidth;
				})
				.attr("stroke-opacity", isHighlighted ? 1 : 0.6);
		});

	// 使用 path 而不是 line，以支持曲线
	// 先添加一个透明的粗路径作为点击区域
	linkEnter
		.append("path")
		.attr("class", "link-hitarea")
		.attr("fill", "none")
		.attr("stroke", "transparent")
		.attr("stroke-width", 15)
		.style("cursor", "pointer");

	// 再添加可见的边
	linkEnter
		.append("path")
		.attr("class", "link-line")
		.attr("fill", "none")
		.attr("stroke", (d: any) => {
			const sourceId =
				typeof d.source === "string" ? d.source : (d.source as Node).id;
			const targetId =
				typeof d.target === "string" ? d.target : (d.target as Node).id;
			const edgeId = `${sourceId}-${targetId}`;
			return highlightedEdgeIds.value.has(edgeId) ? "#ff6b6b" : "#999";
		})
		.attr("stroke-opacity", (d: any) => {
			const sourceId =
				typeof d.source === "string" ? d.source : (d.source as Node).id;
			const targetId =
				typeof d.target === "string" ? d.target : (d.target as Node).id;
			const edgeId = `${sourceId}-${targetId}`;
			return highlightedEdgeIds.value.has(edgeId) ? 1 : 0.6;
		})
		.attr("stroke-width", (d: any) => {
			const sourceId =
				typeof d.source === "string" ? d.source : (d.source as Node).id;
			const targetId =
				typeof d.target === "string" ? d.target : (d.target as Node).id;
			const edgeId = `${sourceId}-${targetId}`;
			const baseWidth = Math.sqrt(d.value || 1) + 1;
			return highlightedEdgeIds.value.has(edgeId) ? baseWidth + 2 : baseWidth;
		})
		.style("pointer-events", "none");

	// 添加边的悬浮提示（放在group上）
	linkEnter.append("title").text((d: any) => {
		const sourceLabel =
			typeof d.source === "string" ? d.source : d.source.label || d.source.id;
		const targetLabel =
			typeof d.target === "string" ? d.target : d.target.label || d.target.id;
		let tooltip = `${sourceLabel} → ${targetLabel}\n`;
		tooltip += `类型: ${d.edge_type}\n`;
		if (d.description) tooltip += `描述: ${d.description}\n`;
		if (d.count !== undefined) tooltip += `计数: ${d.count}\n`;
		if (d.refer && d.refer.length > 0) tooltip += `参与: ${d.refer.join(", ")}`;
		return tooltip;
	});

	linkEnter
		.append("text")
		.attr("class", "link-label")
		.attr("text-anchor", "middle")
		.attr("dy", -5)
		.style("font-size", "10px")
		.style("fill", "#666")
		.style("font-weight", "bold")
		.style("pointer-events", "none")
		.text((d) => {
			if (d.count !== undefined) {
				if (showCountLabelOnlyAbove1.value) {
					return d.count > 1 ? d.count : "";
				}
				return d.count;
			}
			return "";
		});

	// UPDATE: 更新现有边的样式
	linkSelection.select(".link-label").text((d) => {
		if (d.count !== undefined) {
			if (showCountLabelOnlyAbove1.value) {
				return d.count > 1 ? d.count : "";
			}
			return d.count;
		}
		return "";
	});
};

const updateNodes = (nodesData: Node[]) => {
	if (!nodeGroup) return;

	// D3 data join
	const nodeSelection = nodeGroup
		.selectAll<SVGGElement, Node>("g")
		.data(nodesData, (d: any) => d.id);

	// EXIT: 移除不再存在的节点
	nodeSelection.exit().remove();

	// ENTER: 添加新节点
	const nodeEnter = nodeSelection
		.enter()
		.append("g")
		.attr("cursor", "pointer")
		.on("click", function (event, d) {
			event.stopPropagation();
			selectedNode.value = d;
			selectedEdge.value = null;
			activeTab.value = "details";
			// 取消边的高亮
			d3.selectAll(".link-line")
				.attr("stroke", "#999")
				.attr("stroke-width", (ld: any) => Math.sqrt(ld.value || 1) + 1);
		})
		.on("mouseenter", function (event, d: any) {
			const isHighlighted = highlightedNodeIds.value.has(d.id);
			d3.select(this)
				.select("path")
				.attr("stroke", isHighlighted ? "#ff0000" : "#409eff")
				.attr("stroke-width", isHighlighted ? 4 : 3);
		})
		.on("mouseleave", function (event, d: any) {
			const isHighlighted = highlightedNodeIds.value.has(d.id);
			d3.select(this)
				.select("path")
				.attr("stroke", isHighlighted ? "#ff0000" : "#fff")
				.attr("stroke-width", isHighlighted ? 3 : 1.5);
		})
		.call(
			d3
				.drag<any, any>()
				.on("start", dragstarted)
				.on("drag", dragged)
				.on("end", dragended)
		);

	nodeEnter
		.append("path")
		.attr(
			"d",
			d3
				.symbol()
				.type((d) => {
					if (d.node_type === "class_master") return d3.symbolSquare;
					if (d.node_type === "class_node") return d3.symbolTriangle;
					return d3.symbolCircle;
				})
				.size((d) => {
					const baseSize = d.size * d.size * 5;
					return highlightedNodeIds.value.has(d.id) ? baseSize * 2 : baseSize;
				})
		)
		.attr("fill", (d) => {
			return highlightedNodeIds.value.has(d.id)
				? "#ff6b6b"
				: colorScale(d.group.toString());
		})
		.attr("stroke", (d) => {
			return highlightedNodeIds.value.has(d.id) ? "#ff0000" : "#fff";
		})
		.attr("stroke-width", (d) => {
			return highlightedNodeIds.value.has(d.id) ? 3 : 1.5;
		});

	nodeEnter
		.append("text")
		.text((d) => d.label)
		.attr("dx", 15)
		.attr("dy", 5)
		.attr("fill", "#333")
		.style("font-size", "12px")
		.style("font-weight", "500")
		.style("pointer-events", "none");

	// 添加节点的悬浮提示
	nodeEnter.append("title").text((d) => {
		let tooltip = `${d.label}\n`;
		tooltip += `类型: ${d.node_type}\n`;
		if (d.description) tooltip += `描述: ${d.description}\n`;
		if (d.classes && d.classes.length > 0)
			tooltip += `类别: ${d.classes.join(", ")}`;
		return tooltip;
	});

	// UPDATE: 更新现有节点（在需要时）
	// 这里可以添加节点属性更新逻辑
};

const fetchTasks = async () => {
	try {
		const res = await axios.get("/api/tasks");
		tasks.value = res.data;
	} catch (err) {
		console.error("Failed to fetch tasks", err);
	}
};

const fetchStats = async () => {
	try {
		const res = await axios.get("/api/stats");
		stats.value = res.data;
	} catch (err) {
		console.error("Failed to fetch stats", err);
	}
};

const submitTask = async () => {
	if (!inputText.value.trim()) return;
	submitting.value = true;
	try {
		await axios.post("/api/tasks", { input_text: inputText.value });
		inputText.value = "";
		ElMessage.success("Task submitted successfully");
		await fetchTasks();
	} catch (err) {
		ElMessage.error("Failed to submit task");
	} finally {
		submitting.value = false;
	}
};

let eventSource: EventSource | null = null;
let reconnectTimer: number | null = null;

const initSSE = () => {
	// 清理已有连接
	if (eventSource) {
		eventSource.close();
	}

	eventSource = new EventSource("/api/events");

	eventSource.onmessage = (event) => {
		try {
			const data = JSON.parse(event.data);

			// 处理不同类型的事件
			switch (data.event_type) {
				case "task_submitted":
					ElMessage.info(`Task ${data.task_id.substring(0, 8)} submitted`);
					fetchTasks();
					break;

				case "progress":
					// 更新进度
					progressMap.value[data.task_id] = data;

					// 任务完成或失败
					if (data.step === "completed") {
						ElMessage.success({
							message: `Task ${data.task_id.substring(
								0,
								8
							)} completed successfully!`,
							duration: 3000,
						});
						// 延迟一下再更新,确保后端数据已经更新
						setTimeout(async () => {
							await fetchTasks();
							await fetchStats();
							// 自动获取增量数据
							await fetchTaskDelta(data.task_id);
							// 使用增量更新而非完全刷新
							const newData = await fetchGraphData();
							if (newData) {
								updateGraph(newData);
							}
						}, 500);
					} else if (data.step === "failed") {
						ElMessage.error({
							message: `Task ${data.task_id.substring(0, 8)} failed: ${
								data.message
							}`,
							duration: 5000,
						});
						setTimeout(() => {
							fetchTasks();
						}, 500);
					}
					break;
			}
		} catch (err) {
			console.error("Failed to parse SSE event", err);
		}
	};

	eventSource.onerror = (err) => {
		console.error("SSE connection error", err);
		eventSource?.close();

		// 重连机制 - 3秒后重连
		if (reconnectTimer) {
			clearTimeout(reconnectTimer);
		}
		reconnectTimer = window.setTimeout(() => {
			console.log("Reconnecting SSE...");
			initSSE();
		}, 3000);
	};

	eventSource.onopen = () => {
		console.log("SSE connection established");
	};
};

const fetchGraphData = async () => {
	try {
		const res = await axios.get("/api/graph");
		return res.data;
	} catch (err) {
		console.error("Failed to fetch graph data", err);
		return null;
	}
};

const refreshGraph = async () => {
	const data = await fetchGraphData();
	if (data) {
		updateGraph(data);
	}
};

// 数据库加载后的处理
const handleDatabaseLoaded = async () => {
	ElMessage.success("数据库已加载，正在刷新图谱...");
	await refreshGraph();
	await fetchStats();
	ElMessage.success("图谱已更新");
};

const updateGraph = (newData: { nodes: Node[]; links: Link[] }) => {
	if (!isGraphInitialized.value) {
		// 首次初始化
		initGraph(newData);
		isGraphInitialized.value = true;
	} else {
		// 增量更新
		incrementalUpdateGraph(newData);
	}
};

const initGraph = (data: { nodes: Node[]; links: Link[] }) => {
	// 初始化图谱（仅在首次调用）
	if (!graphContainer.value) return;

	const width = graphContainer.value.clientWidth;
	const height = graphContainer.value.clientHeight;

	// 保存原始数据
	graphData.value = { nodes: [...data.nodes], links: [...data.links] };

	// 根据选项过滤节点和边
	const { filteredNodes, filteredLinks } = filterGraphData(data);

	// 清理旧的 SVG
	d3.select(graphContainer.value).selectAll("svg").remove();

	svg = d3
		.select(graphContainer.value)
		.append("svg")
		.attr("width", width)
		.attr("height", height);

	container = svg.append("g");

	zoom = d3
		.zoom<SVGSVGElement, unknown>()
		.scaleExtent([0.1, 8])
		.on("zoom", (event) => {
			container.attr("transform", event.transform);
		});

	svg.call(zoom);

	simulation = d3
		.forceSimulation<Node>(filteredNodes)
		.force(
			"link",
			d3
				.forceLink<Node, Link>(filteredLinks)
				.id((d) => d.id)
				.distance(250)
		)
		.force("charge", d3.forceManyBody().strength(-1000))
		.force("center", d3.forceCenter(width / 2, height / 2))
		.force("collision", d3.forceCollide().radius(80));

	// 创建边容器组
	linkGroup = container.append("g").attr("class", "links");

	// 初始化边
	updateLinks(filteredLinks);

	// 创建节点容器组
	nodeGroup = container.append("g").attr("class", "nodes");

	// 初始化节点
	updateNodes(filteredNodes);

	simulation.on("tick", () => {
		// 更新边位置（使用曲线支持多条边）
		linkGroup.selectAll(".link-group").each(function (d: any) {
			const link = d3.select(this);

			// 计算曲线路径
			const dx = d.target.x - d.source.x;
			const dy = d.target.y - d.source.y;
			const dr = Math.sqrt(dx * dx + dy * dy);

			// 如果有多条边连接同样的两个节点，添加曲线偏移
			let curvature = 0;
			if (d.linkTotal > 1) {
				// 计算偏移量：中间的边接近直线，两边的边弯曲更多
				const maxCurvature = 0.5; // 最大曲率
				const step = (2 * maxCurvature) / (d.linkTotal - 1);
				curvature = -maxCurvature + d.linkIndex * step;
			}

			// 使用二次贝塞尔曲线
			const midX = (d.source.x + d.target.x) / 2;
			const midY = (d.source.y + d.target.y) / 2;

			// 计算控制点（垂直于连线方向）
			const offsetX = -dy * curvature;
			const offsetY = dx * curvature;
			const controlX = midX + offsetX;
			const controlY = midY + offsetY;

			const path = `M ${d.source.x},${d.source.y} Q ${controlX},${controlY} ${d.target.x},${d.target.y}`;

			// 更新透明的点击区域和可见的边
			link.select(".link-hitarea").attr("d", path);
			link.select(".link-line").attr("d", path);

			// 更新标签位置（放在曲线的中点）
			link
				.select(".link-label")
				.attr("x", midX + offsetX * 0.5)
				.attr("y", midY + offsetY * 0.5);
		});

		// 更新节点位置
		nodeGroup
			.selectAll("g")
			.attr("transform", (d: any) => `translate(${d.x},${d.y})`);
	});

	// 点击空白处取消选择
	svg.on("click", () => {
		selectedNode.value = null;
		selectedEdge.value = null;
		d3.selectAll(".link-line")
			.attr("stroke", "#999")
			.attr("stroke-width", (d: any) => Math.sqrt(d.value || 1) + 1);
	});
};

// 拖拽相关函数（移到外部以便复用）
function dragstarted(event: any, d: any) {
	if (!event.active) simulation.alphaTarget(0.05).restart();
	d.fx = d.x;
	d.fy = d.y;
}

function dragged(event: any, d: any) {
	d.fx = event.x;
	d.fy = event.y;
}

function dragended(event: any, d: any) {
	if (!event.active) simulation.alphaTarget(0);
	d.fx = null;
	d.fy = null;
}

const resetZoom = () => {
	if (svg && zoom) {
		svg.transition().duration(750).call(zoom.transform, d3.zoomIdentity);
	}
};

// ==================== 搜索功能 ====================

const performKeywordSearch = async () => {
	if (!searchKeyword.value.trim()) {
		ElMessage.warning("Please enter a keyword");
		return;
	}

	searching.value = true;
	try {
		const res = await axios.post("/api/search/keyword", {
			keyword: searchKeyword.value,
			fuzzy: searchFuzzy.value,
			limit: searchLimit.value,
		});

		if (res.data && res.data.length > 0) {
			searchResults.value = formatKeywordSearchResults(res.data);
			ElMessage.success(`Found ${res.data.length} results`);
		} else {
			searchResults.value = "No results found.";
			ElMessage.info("No results found");
		}
	} catch (err: any) {
		ElMessage.error(err.response?.data?.detail || "Search failed");
		searchResults.value = `Error: ${
			err.response?.data?.detail || "Search failed"
		}`;
	} finally {
		searching.value = false;
	}
};

const performNodeQuery = async () => {
	if (!nodeIdQuery.value.trim()) {
		ElMessage.warning("Please enter a node ID");
		return;
	}

	querying.value = true;
	try {
		const res = await axios.get(
			`/api/search/node/${encodeURIComponent(nodeIdQuery.value)}`
		);

		if (res.data) {
			searchResults.value = formatNodeDetail(res.data);
			ElMessage.success("Node details retrieved");
		} else {
			searchResults.value = "Node not found.";
		}
	} catch (err: any) {
		ElMessage.error(err.response?.data?.detail || "Query failed");
		searchResults.value = `Error: ${
			err.response?.data?.detail || "Query failed"
		}`;
	} finally {
		querying.value = false;
	}
};

const performEntityGroupQuery = async () => {
	if (!groupQueryName.value.trim()) {
		ElMessage.warning("Please enter an entity name");
		return;
	}

	querying.value = true;
	try {
		const res = await axios.get(
			`/api/search/entity-group/${encodeURIComponent(groupQueryName.value)}`
		);

		if (res.data) {
			searchResults.value = formatEntityGroup(res.data);
			ElMessage.success("Entity group retrieved");
		} else {
			searchResults.value = "Entity not found.";
		}
	} catch (err: any) {
		ElMessage.error(err.response?.data?.detail || "Query failed");
		searchResults.value = `Error: ${
			err.response?.data?.detail || "Query failed"
		}`;
	} finally {
		querying.value = false;
	}
};

const performClassGroupQuery = async () => {
	if (!groupQueryName.value.trim()) {
		ElMessage.warning("Please enter a class name");
		return;
	}

	querying.value = true;
	try {
		const res = await axios.get(
			`/api/search/class-group/${encodeURIComponent(groupQueryName.value)}`
		);

		if (res.data) {
			searchResults.value = formatClassGroup(res.data);
			ElMessage.success("Class group retrieved");
		} else {
			searchResults.value = "Class not found.";
		}
	} catch (err: any) {
		ElMessage.error(err.response?.data?.detail || "Query failed");
		searchResults.value = `Error: ${
			err.response?.data?.detail || "Query failed"
		}`;
	} finally {
		querying.value = false;
	}
};

const clearSearchResults = () => {
	searchResults.value = null;
	searchKeyword.value = "";
	nodeIdQuery.value = "";
	groupQueryName.value = "";
};

// ==================== 格式化函数 ====================

const formatKeywordSearchResults = (results: any[]) => {
	let output = `====================================\n`;
	output += `KEYWORD SEARCH RESULTS (${results.length} results)\n`;
	output += `====================================\n\n`;

	results.forEach((result, index) => {
		output += `[${index + 1}] ${result.result_type.toUpperCase()}\n`;
		output += `    Matched: "${result.matched_text}"\n`;
		output += `    Score: ${result.score.toFixed(3)}\n`;
		output += `    Context:\n`;
		for (const [key, value] of Object.entries(result.context)) {
			output += `        ${key}: ${value}\n`;
		}
		output += `\n`;
	});

	return output;
};

const formatNodeDetail = (nodeDetail: any) => {
	let output = `====================================\n`;
	output += `NODE DETAIL\n`;
	output += `====================================\n\n`;

	output += `Node ID: ${nodeDetail.node_id}\n`;
	output += `Node Type: ${nodeDetail.node_type}\n\n`;

	output += `--- Node Information ---\n`;
	output += JSON.stringify(nodeDetail.node_info, null, 2) + "\n\n";

	output += `--- One-Hop Relationships (${nodeDetail.one_hop_relationships.length}) ---\n`;
	nodeDetail.one_hop_relationships.forEach((rel: any, index: number) => {
		output += `[${index + 1}] ${rel.source} -> ${rel.target}\n`;
		output += `    Description: ${rel.description}\n`;
		output += `    Count: ${rel.count}\n`;
		if (rel.refer && rel.refer.length > 0) {
			output += `    Refer: ${rel.refer.join(", ")}\n`;
		}
		output += `\n`;
	});

	output += `--- One-Hop Neighbors (${nodeDetail.one_hop_neighbors.length}) ---\n`;
	nodeDetail.one_hop_neighbors.forEach((neighbor: any, index: number) => {
		output += `[${index + 1}] ${neighbor.node_id}\n`;
	});

	output += `\n--- Statistics ---\n`;
	output += `Relationships: ${nodeDetail.statistics.relationships_count}\n`;
	output += `Neighbors: ${nodeDetail.statistics.neighbors_count}\n`;

	return output;
};

const formatEntityGroup = (entityGroup: any) => {
	let output = `====================================\n`;
	output += `ENTITY NODE GROUP\n`;
	output += `====================================\n\n`;

	output += `--- Entity Node ---\n`;
	output += `Name: ${entityGroup.entity.name}\n`;
	output += `Description: ${entityGroup.entity.description}\n`;
	output += `Classes: ${entityGroup.entity.classes.join(", ")}\n\n`;

	output += `Properties:\n`;
	output += JSON.stringify(entityGroup.entity.properties, null, 2) + "\n\n";

	output += `--- Class Nodes (${entityGroup.class_nodes.length}) ---\n`;
	entityGroup.class_nodes.forEach((node: any, index: number) => {
		output += `[${index + 1}] ${node.node_id}\n`;
		output += `    Entity: ${node.entity_name}\n`;
		output += `    Class: ${node.class_name}\n`;
		output += `    Description: ${node.description}\n\n`;
	});

	output += `--- One-Hop Relationships (${entityGroup.one_hop_relationships.length}) ---\n`;
	entityGroup.one_hop_relationships.forEach((rel: any, index: number) => {
		output += `[${index + 1}] ${rel.source} -> ${rel.target}\n`;
		output += `    Description: ${rel.description}\n`;
		output += `    Count: ${rel.count}\n`;
		if (rel.refer && rel.refer.length > 0) {
			output += `    Refer: ${rel.refer.join(", ")}\n`;
		}
		output += `\n`;
	});

	output += `--- Statistics ---\n`;
	output += `Class Nodes: ${entityGroup.statistics.class_nodes_count}\n`;
	output += `Relationships: ${entityGroup.statistics.relationships_count}\n`;

	return output;
};

const formatClassGroup = (classGroup: any) => {
	let output = `====================================\n`;
	output += `CLASS NODE GROUP\n`;
	output += `====================================\n\n`;

	output += `--- Class Master Node ---\n`;
	output += `Class Name: ${classGroup.class_master_node.class_name}\n`;
	output += `Description: ${classGroup.class_master_node.description}\n\n`;

	output += `--- Class Node Instances (${classGroup.class_nodes.length}) ---\n`;
	classGroup.class_nodes.forEach((node: any, index: number) => {
		output += `[${index + 1}] ${node.node_id}\n`;
		output += `    Entity: ${node.entity_name}\n`;
		output += `    Class: ${node.class_name}\n`;
		output += `    Description: ${node.description}\n\n`;
	});

	output += `--- One-Hop Relationships (${classGroup.one_hop_relationships.length}) ---\n`;
	classGroup.one_hop_relationships.forEach((rel: any, index: number) => {
		output += `[${index + 1}] ${rel.source} -> ${rel.target}\n`;
		output += `    Description: ${rel.description}\n`;
		output += `    Count: ${rel.count}\n`;
		if (rel.refer && rel.refer.length > 0) {
			output += `    Refer: ${rel.refer.join(", ")}\n`;
		}
		output += `\n`;
	});

	output += `--- Statistics ---\n`;
	output += `Instances: ${classGroup.statistics.instances_count}\n`;
	output += `Relationships: ${classGroup.statistics.relationships_count}\n`;

	return output;
};

// ==================== 左侧面板宽度调整 ====================

const startResize = (event: MouseEvent) => {
	isResizing.value = true;
	document.addEventListener("mousemove", handleResizeDrag);
	document.addEventListener("mouseup", stopResize);
	event.preventDefault();
};

const handleResizeDrag = (event: MouseEvent) => {
	if (!isResizing.value) return;

	// 计算新的宽度
	const newWidth = event.clientX;

	// 限制在最小和最大宽度之间
	if (newWidth >= minAsideWidth && newWidth <= maxAsideWidth) {
		asideWidth.value = newWidth;
		// 保存到 localStorage
		localStorage.setItem("asideWidth", newWidth.toString());
	}
};

const stopResize = () => {
	isResizing.value = false;
	document.removeEventListener("mousemove", handleResizeDrag);
	document.removeEventListener("mouseup", stopResize);
};

// 从 localStorage 加载保存的宽度
const loadAsideWidth = () => {
	const savedWidth = localStorage.getItem("asideWidth");
	if (savedWidth) {
		const width = parseInt(savedWidth);
		if (width >= minAsideWidth && width <= maxAsideWidth) {
			asideWidth.value = width;
		}
	}
};

onMounted(async () => {
	// 加载保存的侧边栏宽度
	loadAsideWidth();
	await fetchTasks();
	await fetchStats();
	initSSE();

	// 初始化图谱
	const data = await fetchGraphData();
	if (data) {
		updateGraph(data);
	}

	// 窗口大小改变时只调整 SVG 和力的中心，不重新渲染
	window.addEventListener("resize", handleResize);
});

const handleResize = () => {
	if (graphContainer.value && svg && simulation) {
		const width = graphContainer.value.clientWidth;
		const height = graphContainer.value.clientHeight;
		svg.attr("width", width).attr("height", height);
		simulation.force("center", d3.forceCenter(width / 2, height / 2));
		simulation.alpha(0.3).restart();
	}
};

onUnmounted(() => {
	// 清理SSE连接
	if (eventSource) {
		eventSource.close();
		eventSource = null;
	}

	// 清理重连定时器
	if (reconnectTimer) {
		clearTimeout(reconnectTimer);
		reconnectTimer = null;
	}

	// 清理resize监听
	window.removeEventListener("resize", handleResize);

	// 清理拖拽监听
	document.removeEventListener("mousemove", handleResizeDrag);
	document.removeEventListener("mouseup", stopResize);

	// 停止模拟
	if (simulation) {
		simulation.stop();
	}
});
</script>

<style scoped>
.layout-container {
	height: 100vh;
	width: 100vw;
	display: flex;
	flex-direction: column;
	overflow: hidden;
}
.header {
	background-color: #409eff;
	color: white;
	display: flex;
	align-items: center;
	justify-content: space-between;
	padding: 0 20px;
	height: 60px;
	flex-shrink: 0;
}
.logo {
	font-size: 22px;
	font-weight: bold;
}
.content-container {
	flex: 1;
	display: flex;
	overflow: hidden;
}
.aside {
	border-right: none;
	background-color: #fff;
	flex-shrink: 0;
	display: flex;
	flex-direction: column;
	overflow: hidden;
	min-width: 300px;
	max-width: 1200px;
	width: 600px; /* 默认宽度，会被内联样式覆盖 */
}

/* 可拖拽的分隔线 */
.resize-handle {
	width: 5px;
	background-color: #e6e6e6;
	cursor: col-resize;
	position: relative;
	flex-shrink: 0;
	transition: background-color 0.2s;
	z-index: 100;
}

.resize-handle:hover {
	background-color: #409eff;
}

.resize-handle.resizing {
	background-color: #409eff;
}

/* 拖拽时禁用文本选择 */
.resize-handle.resizing ~ * {
	user-select: none;
	pointer-events: none;
}
.tabs-container {
	flex: 1;
	display: flex;
	flex-direction: column;
	overflow: hidden;
}
.tabs-container :deep(.el-tabs__header) {
	flex-shrink: 0;
	margin: 0;
	padding: 0 20px;
}
.tabs-container :deep(.el-tabs__content) {
	flex: 1;
	overflow: hidden;
	padding: 0;
}
.tabs-container :deep(.el-tab-pane) {
	height: 100%;
	overflow: hidden;
}
.tab-pane-content {
	height: 100%;
	overflow-y: auto;
	overflow-x: hidden;
	padding: 20px;
}

/* 自定义滚动条样式 */
.tab-pane-content::-webkit-scrollbar {
	width: 8px;
}

.tab-pane-content::-webkit-scrollbar-track {
	background: #f1f1f1;
	border-radius: 4px;
}

.tab-pane-content::-webkit-scrollbar-thumb {
	background: #c1c1c1;
	border-radius: 4px;
}

.tab-pane-content::-webkit-scrollbar-thumb:hover {
	background: #a8a8a8;
}
.main-viz {
	flex: 1;
	padding: 0;
	position: relative;
	background-color: #f5f7fa;
	overflow: hidden;
}
#graph-container {
	width: 100%;
	height: 100%;
}
.viz-controls {
	position: absolute;
	top: 20px;
	right: 20px;
	z-index: 10;
}
.task-submit {
	margin-bottom: 20px;
}
.task-card {
	font-size: 14px;
}
.task-header {
	display: flex;
	justify-content: space-between;
	align-items: center;
	margin-bottom: 10px;
}
.task-id {
	font-family: monospace;
	color: #666;
	font-weight: bold;
}
.task-text {
	color: #444;
	margin: 10px 0;
	line-height: 1.4;
}
.progress-details {
	font-size: 12px;
	color: #666;
}
.progress-msg {
	display: flex;
	align-items: center;
	gap: 6px;
	color: #409eff;
	margin-bottom: 4px;
}
.progress-step {
	color: #999;
	font-size: 11px;
}
.task-completed {
	padding-top: 8px;
	border-top: 1px solid #f0f0f0;
}
.task-failed {
	padding-top: 8px;
}
.node-details h3,
.edge-details h3 {
	margin-top: 0;
	color: #303133;
	border-bottom: 2px solid #409eff;
	padding-bottom: 10px;
	display: flex;
	align-items: center;
	gap: 8px;
}
.edge-details {
	padding: 10px 0;
}
.cls-title {
	margin: 15px 0 8px 0;
	color: #409eff;
	font-size: 16px;
}
.mt-2 {
	margin-top: 0.5rem;
}
.mt-4 {
	margin-top: 1rem;
}
.mb-1 {
	margin-bottom: 0.25rem;
}
.mb-4 {
	margin-bottom: 1rem;
}
.ml-2 {
	margin-left: 0.5rem;
}
.mr-1 {
	margin-right: 0.25rem;
}
.w-full {
	width: 100%;
}
.options-container {
	padding: 10px 0;
}
.options-container h3 {
	margin-top: 0;
	color: #303133;
	font-size: 18px;
	font-weight: 600;
}
.option-item {
	padding: 15px 0;
}
.option-desc {
	margin-top: 8px;
	font-size: 13px;
	color: #909399;
	line-height: 1.5;
}
.link-group:hover .link-line {
	stroke: #67c23a !important;
	stroke-width: 3px !important;
}
.link-label {
	user-select: none;
}
.empty-state {
	padding: 40px 20px;
	text-align: center;
}
.completed-info {
	display: flex;
	align-items: center;
	gap: 8px;
	flex-wrap: wrap;
}
.delta-stats {
	display: flex;
	gap: 4px;
	flex-wrap: wrap;
}
.increments-container {
	padding: 10px 0;
}
.increments-container h3 {
	margin-top: 0;
	color: #303133;
	font-size: 18px;
	font-weight: 600;
}
.delta-card {
	font-size: 14px;
	transition: all 0.3s;
}
.delta-card.active {
	border: 2px solid #409eff;
	box-shadow: 0 0 10px rgba(64, 158, 255, 0.3);
}
.delta-header {
	display: flex;
	justify-content: space-between;
	align-items: center;
}
.delta-task-id {
	font-family: monospace;
	font-weight: bold;
	color: #666;
}
.delta-content {
	margin-top: 12px;
}
.entity-item,
.relationship-item {
	padding: 8px;
	border-bottom: 1px solid #f0f0f0;
	display: flex;
	align-items: center;
}
.entity-item:last-child,
.relationship-item:last-child {
	border-bottom: none;
}
.relationship-main {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
}
.relationship-refer {
	margin-top: 8px;
	margin-left: 24px;
	display: flex;
	align-items: center;
	gap: 8px;
}
.refer-label {
	font-size: 12px;
	color: #909399;
	font-weight: 500;
}
.mx-1 {
	margin-left: 0.25rem;
	margin-right: 0.25rem;
}
.ml-1 {
	margin-left: 0.25rem;
}

/* 任务阶段详情对话框样式 */
.stages-dialog {
	padding: 10px 0;
}
.stage-title {
	display: flex;
	align-items: center;
	font-weight: 500;
}
.stage-content {
	padding: 16px 0;
}
.card-header {
	display: flex;
	align-items: center;
	font-weight: 600;
	font-size: 14px;
}
.llm-response {
	background: #f5f7fa;
	padding: 12px;
	border-radius: 4px;
	font-size: 12px;
	max-height: 400px;
	overflow-y: auto;
	white-space: pre-wrap;
	word-wrap: break-word;
	font-family: "Courier New", Courier, monospace;
	line-height: 1.5;
}

.llm-response::-webkit-scrollbar {
	width: 6px;
}

.llm-response::-webkit-scrollbar-track {
	background: #e8eaed;
	border-radius: 3px;
}

.llm-response::-webkit-scrollbar-thumb {
	background: #c1c1c1;
	border-radius: 3px;
}

.llm-response::-webkit-scrollbar-thumb:hover {
	background: #a8a8a8;
}
.entities-list,
.relationships-list {
	max-height: 500px;
	overflow-y: auto;
}

/* 自定义dialog内滚动条样式 */
.entities-list::-webkit-scrollbar,
.relationships-list::-webkit-scrollbar {
	width: 6px;
}

.entities-list::-webkit-scrollbar-track,
.relationships-list::-webkit-scrollbar-track {
	background: #f1f1f1;
	border-radius: 3px;
}

.entities-list::-webkit-scrollbar-thumb,
.relationships-list::-webkit-scrollbar-thumb {
	background: #c1c1c1;
	border-radius: 3px;
}

.entities-list::-webkit-scrollbar-thumb:hover,
.relationships-list::-webkit-scrollbar-thumb:hover {
	background: #a8a8a8;
}
.entity-header {
	display: flex;
	align-items: center;
	flex-wrap: wrap;
	gap: 4px;
}
.entity-desc {
	color: #606266;
	font-size: 13px;
}
.entity-props {
	border-top: 1px dashed #dcdfe6;
	padding-top: 8px;
}
.loading-container {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: center;
	padding: 60px 0;
	color: #909399;
}

/* 搜索页面样式 */
.search-container h3 {
	margin-top: 0;
	color: #303133;
	font-size: 20px;
	font-weight: 600;
	display: flex;
	align-items: center;
	gap: 8px;
}
.search-section {
	padding: 10px 0;
}
.search-section h4 {
	margin: 0 0 12px 0;
	color: #606266;
	font-size: 16px;
	font-weight: 600;
}
.search-options {
	display: flex;
	align-items: center;
	gap: 8px;
}
.search-results {
	margin-top: 20px;
	margin-bottom: 20px;
}
.result-header {
	display: flex;
	justify-content: space-between;
	align-items: center;
	margin-bottom: 12px;
}
.result-header h4 {
	margin: 0;
	color: #303133;
	font-size: 16px;
	font-weight: 600;
}
.result-content {
	background: #f5f7fa;
	border: 1px solid #dcdfe6;
	border-radius: 4px;
	padding: 16px;
	max-height: 400px;
	overflow-y: auto;
	overflow-x: hidden;
}

.result-content::-webkit-scrollbar {
	width: 6px;
}

.result-content::-webkit-scrollbar-track {
	background: #e8eaed;
	border-radius: 3px;
}

.result-content::-webkit-scrollbar-thumb {
	background: #c1c1c1;
	border-radius: 3px;
}

.result-content::-webkit-scrollbar-thumb:hover {
	background: #a8a8a8;
}
.result-text {
	margin: 0;
	font-family: "Courier New", Courier, monospace;
	font-size: 13px;
	line-height: 1.6;
	color: #303133;
	white-space: pre-wrap;
	word-wrap: break-word;
}
.mb-2 {
	margin-bottom: 0.5rem;
}
</style>
