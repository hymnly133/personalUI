<template>
	<div class="database-manager">
		<el-card>
			<template #header>
				<div class="card-header">
					<span
						><el-icon><Coin /></el-icon> 数据库管理</span
					>
					<el-button type="primary" size="small" @click="refreshDatabases">
						<el-icon><Refresh /></el-icon> 刷新
					</el-button>
				</div>
			</template>

			<!-- 数据库状态 -->
			<div class="database-status mb-3">
				<el-descriptions :column="2" border size="small">
					<el-descriptions-item label="当前状态">
						<el-tag :type="dbStatus.initialized ? 'success' : 'warning'">
							{{ dbStatus.initialized ? "已初始化" : "未初始化" }}
						</el-tag>
					</el-descriptions-item>
					<el-descriptions-item label="自动保存">
						<el-switch
							v-model="dbStatus.auto_save_enabled"
							@change="toggleAutoSave"
							active-text="开启"
							inactive-text="关闭"
						/>
					</el-descriptions-item>
					<el-descriptions-item label="默认路径" :span="2">
						<el-text size="small" type="info">{{
							dbStatus.default_path
						}}</el-text>
					</el-descriptions-item>
				</el-descriptions>
			</div>

			<!-- 统计信息 -->
			<div v-if="dbStatus.statistics" class="statistics mb-3">
				<el-row :gutter="10">
					<el-col :span="8">
						<el-statistic
							title="类定义"
							:value="dbStatus.statistics.system?.classes || 0"
						/>
					</el-col>
					<el-col :span="8">
						<el-statistic
							title="实体"
							:value="dbStatus.statistics.graph?.entities || 0"
						/>
					</el-col>
					<el-col :span="8">
						<el-statistic
							title="关系"
							:value="dbStatus.statistics.graph?.relationships || 0"
						/>
					</el-col>
				</el-row>
			</div>

			<el-divider />

			<!-- 操作按钮 -->
			<div class="actions mb-3">
				<el-space wrap>
					<el-button type="success" @click="showCreateDialog">
						<el-icon><Plus /></el-icon> 新建数据库
					</el-button>
					<el-button type="primary" @click="saveCurrentDatabase">
						<el-icon><Download /></el-icon> 保存当前数据库
					</el-button>
				</el-space>
			</div>

			<el-divider />

			<!-- 数据库列表 -->
			<div class="database-list">
				<h4>可用数据库 ({{ databases.length }})</h4>
				<el-table
					:data="databases"
					stripe
					style="width: 100%"
					v-loading="loading"
				>
					<el-table-column type="index" width="50" />
					<el-table-column prop="file_name" label="文件名" min-width="180">
						<template #default="{ row }">
							<el-text :type="row.is_default ? 'primary' : 'default'">
								{{ row.file_name }}
							</el-text>
							<el-tag
								v-if="row.is_default"
								size="small"
								type="success"
								class="ml-2"
							>
								当前
							</el-tag>
						</template>
					</el-table-column>
					<el-table-column prop="file_size" label="大小" width="120">
						<template #default="{ row }">
							{{ formatFileSize(row.file_size) }}
						</template>
					</el-table-column>
					<el-table-column prop="modified_time" label="修改时间" width="180">
						<template #default="{ row }">
							{{ formatDate(row.modified_time) }}
						</template>
					</el-table-column>
					<el-table-column label="操作" width="220" fixed="right">
						<template #default="{ row }">
							<el-button-group>
								<el-button
									size="small"
									type="primary"
									@click="loadDatabase(row.file_name)"
									:disabled="row.is_default"
								>
									<el-icon><FolderOpened /></el-icon>
									加载
								</el-button>
								<el-button size="small" @click="showRenameDialog(row)">
									<el-icon><Edit /></el-icon>
									重命名
								</el-button>
								<el-button
									size="small"
									type="danger"
									@click="deleteDatabase(row.file_name)"
									:disabled="row.is_default"
								>
									<el-icon><Delete /></el-icon>
									删除
								</el-button>
							</el-button-group>
						</template>
					</el-table-column>
				</el-table>
			</div>
		</el-card>

		<!-- 新建数据库对话框 -->
		<el-dialog v-model="createDialogVisible" title="新建数据库" width="500px">
			<el-form :model="createForm" label-width="100px">
				<el-form-item label="文件名">
					<el-input
						v-model="createForm.file_name"
						placeholder="留空使用默认名称 graph_database.pkl"
						clearable
					>
						<template #suffix>.pkl</template>
					</el-input>
				</el-form-item>
				<el-alert
					title="注意"
					type="warning"
					:closable="false"
					show-icon
					class="mb-3"
				>
					创建新数据库将会清空当前图谱数据，请先保存当前数据库！
				</el-alert>
			</el-form>
			<template #footer>
				<el-button @click="createDialogVisible = false">取消</el-button>
				<el-button type="primary" @click="createDatabase">确认创建</el-button>
			</template>
		</el-dialog>

		<!-- 重命名对话框 -->
		<el-dialog v-model="renameDialogVisible" title="重命名数据库" width="500px">
			<el-form :model="renameForm" label-width="100px">
				<el-form-item label="原文件名">
					<el-text>{{ renameForm.old_name }}</el-text>
				</el-form-item>
				<el-form-item label="新文件名">
					<el-input
						v-model="renameForm.new_name"
						placeholder="输入新文件名"
						clearable
					>
						<template #suffix>.pkl</template>
					</el-input>
				</el-form-item>
			</el-form>
			<template #footer>
				<el-button @click="renameDialogVisible = false">取消</el-button>
				<el-button type="primary" @click="renameDatabase">确认重命名</el-button>
			</template>
		</el-dialog>
	</div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
	Coin,
	Refresh,
	Plus,
	Download,
	FolderOpened,
	Edit,
	Delete,
} from "@element-plus/icons-vue";
import axios from "axios";

const API_BASE = "http://localhost:8000";

// 数据库列表
const databases = ref<any[]>([]);
const loading = ref(false);

// 数据库状态
const dbStatus = ref<any>({
	initialized: false,
	auto_save_enabled: true,
	default_path: "",
	statistics: null,
});

// 对话框状态
const createDialogVisible = ref(false);
const renameDialogVisible = ref(false);

// 表单数据
const createForm = ref({
	file_name: "",
});

const renameForm = ref({
	old_name: "",
	new_name: "",
});

// 获取数据库列表
const fetchDatabases = async () => {
	loading.value = true;
	try {
		const response = await axios.get(`${API_BASE}/api/database/list`);
		databases.value = response.data;
	} catch (error: any) {
		ElMessage.error(`获取数据库列表失败: ${error.message}`);
	} finally {
		loading.value = false;
	}
};

// 获取数据库状态
const fetchStatus = async () => {
	try {
		const response = await axios.get(`${API_BASE}/api/database/status`);
		dbStatus.value = response.data;
	} catch (error: any) {
		ElMessage.error(`获取数据库状态失败: ${error.message}`);
	}
};

// 刷新数据
const refreshDatabases = async () => {
	await Promise.all([fetchDatabases(), fetchStatus()]);
	ElMessage.success("刷新成功");
};

// 切换自动保存
const toggleAutoSave = async (enabled: boolean) => {
	try {
		await axios.put(`${API_BASE}/api/database/auto-save`, {
			enabled,
		});
		ElMessage.success(`自动保存已${enabled ? "启用" : "禁用"}`);
	} catch (error: any) {
		ElMessage.error(`设置自动保存失败: ${error.message}`);
		// 恢复原状态
		dbStatus.value.auto_save_enabled = !enabled;
	}
};

// 显示新建对话框
const showCreateDialog = () => {
	createForm.value.file_name = "";
	createDialogVisible.value = true;
};

// 创建新数据库
const createDatabase = async () => {
	try {
		const fileName = createForm.value.file_name
			? createForm.value.file_name.endsWith(".pkl")
				? createForm.value.file_name
				: `${createForm.value.file_name}.pkl`
			: null;

		const response = await axios.post(`${API_BASE}/api/database/create`, {
			file_name: fileName,
		});

		ElMessage.success(response.data.message);
		createDialogVisible.value = false;
		await refreshDatabases();
	} catch (error: any) {
		ElMessage.error(
			`创建数据库失败: ${error.response?.data?.detail || error.message}`
		);
	}
};

// 保存当前数据库
const saveCurrentDatabase = async () => {
	try {
		const response = await axios.post(`${API_BASE}/api/database/save`, {});
		ElMessage.success(response.data.message);
		await refreshDatabases();
	} catch (error: any) {
		ElMessage.error(
			`保存数据库失败: ${error.response?.data?.detail || error.message}`
		);
	}
};

// 加载数据库
const loadDatabase = async (fileName: string) => {
	try {
		await ElMessageBox.confirm(
			`确定要加载数据库 "${fileName}" 吗？当前数据将被替换！`,
			"确认加载",
			{
				confirmButtonText: "确定",
				cancelButtonText: "取消",
				type: "warning",
			}
		);

		const response = await axios.post(`${API_BASE}/api/database/load`, {
			file_name: fileName,
		});

		ElMessage.success(response.data.message);
		await refreshDatabases();

		// 通知父组件刷新图谱
		emit("database-loaded");
	} catch (error: any) {
		if (error !== "cancel") {
			ElMessage.error(
				`加载数据库失败: ${error.response?.data?.detail || error.message}`
			);
		}
	}
};

// 显示重命名对话框
const showRenameDialog = (row: any) => {
	renameForm.value.old_name = row.file_name;
	renameForm.value.new_name = row.file_name.replace(".pkl", "");
	renameDialogVisible.value = true;
};

// 重命名数据库
const renameDatabase = async () => {
	try {
		const newName = renameForm.value.new_name.endsWith(".pkl")
			? renameForm.value.new_name
			: `${renameForm.value.new_name}.pkl`;

		const response = await axios.put(`${API_BASE}/api/database/rename`, {
			old_name: renameForm.value.old_name,
			new_name: newName,
		});

		ElMessage.success(response.data.message);
		renameDialogVisible.value = false;
		await refreshDatabases();
	} catch (error: any) {
		ElMessage.error(
			`重命名失败: ${error.response?.data?.detail || error.message}`
		);
	}
};

// 删除数据库
const deleteDatabase = async (fileName: string) => {
	try {
		await ElMessageBox.confirm(
			`确定要删除数据库 "${fileName}" 吗？此操作不可恢复！`,
			"确认删除",
			{
				confirmButtonText: "确定",
				cancelButtonText: "取消",
				type: "error",
			}
		);

		const response = await axios.delete(`${API_BASE}/api/database/${fileName}`);
		ElMessage.success(response.data.message);
		await refreshDatabases();
	} catch (error: any) {
		if (error !== "cancel") {
			ElMessage.error(
				`删除失败: ${error.response?.data?.detail || error.message}`
			);
		}
	}
};

// 格式化文件大小
const formatFileSize = (bytes: number): string => {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
	return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
};

// 格式化日期
const formatDate = (timestamp: number): string => {
	const date = new Date(timestamp * 1000);
	return date.toLocaleString("zh-CN", {
		year: "numeric",
		month: "2-digit",
		day: "2-digit",
		hour: "2-digit",
		minute: "2-digit",
	});
};

// 定义事件
const emit = defineEmits(["database-loaded"]);

// 初始化
onMounted(() => {
	refreshDatabases();
});
</script>

<style scoped>
.database-manager {
	height: 100%;
	overflow-y: auto;
}

.card-header {
	display: flex;
	justify-content: space-between;
	align-items: center;
}

.mb-3 {
	margin-bottom: 16px;
}

.ml-2 {
	margin-left: 8px;
}

.actions {
	display: flex;
	gap: 10px;
}

.database-list {
	margin-top: 16px;
}

.database-status {
	background: #f5f7fa;
	padding: 12px;
	border-radius: 4px;
}

.statistics {
	padding: 12px;
	background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
	border-radius: 8px;
	color: white;
}

.statistics :deep(.el-statistic__head) {
	color: rgba(255, 255, 255, 0.8);
}

.statistics :deep(.el-statistic__content) {
	color: white;
}
</style>
