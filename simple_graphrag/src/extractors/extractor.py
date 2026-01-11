"""
实体和关系提取器，使用LLM从文本中提取实体和关系
"""

import re
import logging
from typing import List, Tuple, Optional, Dict
from pathlib import Path

from ..models.entity import Entity, System
from ..models.relationship import Relationship
from ..llm.client import LLMClient
from ..utils.logger import get_logger

logger = get_logger(__name__)


class GraphExtractor:
    """图提取器，从文本中提取实体和关系"""

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_template_path: Path,
        classes: List[str],
        system: System,
        tuple_delimiter: str = "|",
        record_delimiter: str = "^",
        completion_delimiter: str = "DONE",
        language: str = "中文",
        base_entities: Optional[List[Dict]] = None,
        enable_check: bool = True,
        check_template_path: Optional[Path] = None,
    ):
        """
        初始化提取器

        Args:
            llm_client: LLM客户端
            prompt_template_path: 提示词模板文件路径
            classes: 类列表
            system: System（用于类/属性定义、必选属性补齐等）
            tuple_delimiter: 元组分隔符
            record_delimiter: 记录分隔符
            completion_delimiter: 完成标记
            language: 输出语言
            base_entities: 基础实体列表（可选），格式: [{"name": "...", "description": "...", "classes": [...]}, ...]
            enable_check: 是否启用检查步骤（默认True）
            check_template_path: 检查提示词模板路径（可选，默认为prompt_template_path同目录下的check_extraction.txt）
        """
        self.llm_client = llm_client
        self.classes = classes
        self.system = system
        self.tuple_delimiter = tuple_delimiter
        self.record_delimiter = record_delimiter
        self.completion_delimiter = completion_delimiter
        self.language = language
        self.base_entities = base_entities or []
        self.enable_check = enable_check

        # 加载提示词模板
        self.prompt_template = LLMClient.load_prompt_template(prompt_template_path)

        # 加载检查提示词模板
        if enable_check:
            if check_template_path is None:
                # 默认在同目录下查找check_extraction.txt
                check_template_path = (
                    prompt_template_path.parent / "check_extraction.txt"
                )

            if check_template_path.exists():
                self.check_template = LLMClient.load_prompt_template(
                    check_template_path
                )
                logger.debug(f"已加载检查提示词: {check_template_path}")
            else:
                logger.warning(
                    f"检查提示词文件不存在: {check_template_path}，将禁用检查步骤"
                )
                self.enable_check = False

    def _generate_classes_info(self) -> str:
        """生成类和属性的信息字符串"""
        info_lines = []

        for class_name in self.classes:
            class_def = self.system.get_class_definition(class_name)
            if class_def:
                props_info = []
                for prop_def in class_def.properties:
                    required_str = "必选" if prop_def.required else "可选"
                    value_required_str = (
                        "值必填" if prop_def.value_required else "值可选"
                    )
                    props_info.append(
                        f"    - {prop_def.name} ({required_str}, {value_required_str}): {prop_def.description or '无描述'}"
                    )

                props_str = "\n".join(props_info) if props_info else "    - 无属性"
                info_lines.append(
                    f"- {class_name}: {class_def.description or '无描述'}\n{props_str}"
                )

        return "\n\n".join(info_lines)

    def _format_base_entities(self) -> str:
        """
        格式化基础实体信息为字符串

        Returns:
            格式化的基础实体信息字符串
        """
        if not self.base_entities:
            return "无预定义基础实体"

        lines = [
            "The following entities are pre-defined in the base architecture. If these entities are mentioned in the text, use their pre-defined classes:"
        ]
        for entity in self.base_entities:
            entity_name = entity.get("name", "")
            entity_desc = entity.get("description", "")
            entity_classes = entity.get("classes", [])
            classes_str = ", ".join(entity_classes) if entity_classes else "无类"
            lines.append(f'- "{entity_name}" [{classes_str}]')

        return "\n".join(lines)

    def _check_extraction(
        self, input_text: str, extraction_result: str, entity_types: str
    ) -> str:
        """
        检查和优化提取结果

        Args:
            input_text: 原始输入文本
            extraction_result: 第一次提取的结果
            entity_types: 可用的类列表

        Returns:
            优化后的提取结果
        """
        logger.debug("调用检查LLM优化提取结果...")

        response = self.llm_client.extract_text(
            prompt_template=self.check_template,
            temperature=0.3,  # 使用较低的温度以获得更稳定的结果
            input_text=input_text,
            extraction_result=extraction_result,
            entity_types=entity_types,
        )

        return response

    def extract(self, text: str) -> Tuple[List[Entity], List[Relationship]]:
        """
        从文本中提取实体和关系（三步提取）

        Args:
            text: 输入文本

        Returns:
            (实体列表, 关系列表) 元组
        """
        logger.info("开始三步提取：实体 -> 类属性 -> 关系")
        logger.debug(f"输入文本长度: {len(text)} 字符")
        logger.debug(f"输入文本预览: {text[:200]}...")

        # 准备模板变量
        classes_str = ",".join(self.classes)
        classes_info = self._generate_classes_info()
        base_entities_info = self._format_base_entities()
        logger.debug(f"类列表: {classes_str}")
        logger.debug(
            f"分隔符配置: tuple_delimiter='{self.tuple_delimiter}', record_delimiter='{self.record_delimiter}', completion_delimiter='{self.completion_delimiter}'"
        )
        logger.debug(f"基础实体数量: {len(self.base_entities)}")

        # 调用LLM提取
        logger.debug("调用LLM进行三步提取...")
        response = self.llm_client.extract_text(
            prompt_template=self.prompt_template,
            input_text=text,
            entity_types=classes_str,  # LLM客户端仍使用entity_types参数名
            tuple_delimiter=self.tuple_delimiter,
            record_delimiter=self.record_delimiter,
            completion_delimiter=self.completion_delimiter,
            language=self.language,
            classes_info=classes_info,  # 添加类和属性信息
            base_entities_info=base_entities_info,  # 添加基础实体信息
        )

        logger.debug(f"LLM响应长度: {len(response)} 字符")
        logger.debug(f"LLM响应内容:\n{response}")

        # 如果启用检查，进行二次优化
        if self.enable_check:
            logger.info("=" * 60)
            logger.info("开始检查和优化提取结果...")
            logger.info("=" * 60)

            checked_response = self._check_extraction(text, response, classes_str)

            logger.debug(f"检查后响应长度: {len(checked_response)} 字符")
            logger.debug(f"检查后响应内容:\n{checked_response}")

            # 使用检查后的结果
            response = checked_response
            logger.info("检查优化完成")
            logger.info("=" * 60)

        # 解析响应
        logger.debug("开始解析LLM响应...")
        entities, relationships = self._parse_response(response)

        logger.info(f"提取完成: {len(entities)} 个实体, {len(relationships)} 个关系")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("提取的实体:")
            for entity in entities:
                class_names = [c.class_name for c in entity.classes]
                logger.debug(
                    f"  - {entity.name} (类: {class_names}): {entity.description[:100]}"
                )
            logger.debug("提取的关系:")
            for rel in relationships:
                logger.debug(f"  - {rel.source} -> {rel.target} (次数: {rel.count})")

        return entities, relationships

    def _parse_response(self, response: str) -> Tuple[List[Entity], List[Relationship]]:
        """
        解析LLM响应，三步提取：实体 -> 类属性 -> 关系

        Args:
            response: LLM返回的文本

        Returns:
            (实体列表, 关系列表) 元组
        """
        logger.debug("开始四步解析响应...")

        # 移除完成标记
        original_response = response
        response = response.replace(self.completion_delimiter, "").strip()
        if response != original_response:
            logger.debug(f"移除了完成标记: {self.completion_delimiter}")

        # 处理模板中的 **{record_delimiter}** 格式
        response = response.replace("**", "")

        # 按SECTION_DELIMITER分割四个步骤
        sections = response.split("SECTION_DELIMITER")
        if len(sections) < 4:
            logger.debug(
                f"响应未包含四个步骤（只有{len(sections)}个），自动补充 STEP 0..."
            )
            # 兼容旧的三步格式
            if len(sections) >= 3:
                # 插入空的 STEP 0
                sections.insert(0, "NO_NEW_PROPERTIES")
            else:
                logger.warning(f"响应格式不正确，尝试按传统方式解析...")
                return self._parse_response_legacy(response)

        step0_text = sections[0].strip()  # 属性建议
        step1_text = sections[1].strip()  # 实体
        step2_text = sections[2].strip()  # 类属性
        step3_text = sections[3].strip()  # 关系

        # 第零步：解析并应用属性建议
        logger.debug("=== 第零步：解析属性建议 ===")
        has_new_properties = "NO_NEW_PROPERTIES" not in step0_text
        if has_new_properties:
            logger.info("📝 检测到新属性建议")
        self._parse_and_apply_property_suggestions(step0_text)

        # 第一步：解析实体
        logger.debug("=== 第一步：解析实体 ===")
        logger.debug(f"STEP 1 原始文本:\n{step1_text[:500]}")
        entities_dict = {}  # entity_name -> Entity
        step1_records = self._split_records(step1_text)
        logger.debug(f"STEP 1 分割得到 {len(step1_records)} 条记录")
        for i, record in enumerate(step1_records):
            logger.debug(f"处理 STEP 1 记录 {i+1}: {record[:100]}")
            entity = self._parse_entity_step1(record)
            if entity:
                entities_dict[entity.name] = entity
                logger.debug(f"解析实体成功: {entity.name} - {entity.description[:50]}")
            else:
                logger.warning(f"解析实体失败: {record[:100]}")

        logger.debug(
            f"STEP 1 解析完成，共解析 {len(entities_dict)} 个实体: {list(entities_dict.keys())}"
        )

        # 第二步：解析类属性
        logger.debug("=== 第二步：解析类属性 ===")
        step2_records = self._split_records(step2_text)
        for record in step2_records:
            self._parse_class_property(record, entities_dict)

        # 第三步：解析关系
        logger.debug("=== 第三步：解析关系 ===")
        relationships = []
        step3_records = self._split_records(step3_text)
        for record in step3_records:
            relationship = self._parse_relationship(record)
            if relationship:
                relationships.append(relationship)
                logger.debug(
                    f"解析关系: {relationship.source} -> {relationship.target}"
                )

        # 对所有实体进行最终验证
        entities = []
        logger.debug(f"开始验证 {len(entities_dict)} 个实体")
        for entity in entities_dict.values():
            try:
                # 现在验证类和属性
                entity.validate_against_system(self.system, strict=False)
                entities.append(entity)
                logger.debug(f"实体 {entity.name} 验证通过，已添加到结果列表")
            except Exception as e:
                logger.warning(f"实体 {entity.name} 验证失败，跳过: {e}")
                logger.debug(
                    f"实体 {entity.name} 的类: {[c.class_name for c in entity.classes]}"
                )

        logger.info(
            f"四步解析完成: {len(entities)} 个实体, {len(relationships)} 个关系"
        )
        return entities, relationships

    def _parse_and_apply_property_suggestions(self, step0_text: str) -> None:
        """
        解析 STEP 0 的属性建议并应用到 System 中

        Args:
            step0_text: STEP 0 的文本内容
        """
        # 检查是否没有新属性建议
        if "NO_NEW_PROPERTIES" in step0_text:
            logger.debug("无需添加新属性")
            return

        logger.debug(f"STEP 0 原始文本:\n{step0_text[:500]}")

        # 分割记录
        records = self._split_records(step0_text)
        logger.debug(f"STEP 0 分割得到 {len(records)} 条属性建议")

        added_count = 0
        for i, record in enumerate(records):
            logger.debug(f"处理 STEP 0 记录 {i+1}: {record[:100]}")

            # 解析单条属性建议
            prop_suggestion = self._parse_property_suggestion_record(record)
            if prop_suggestion:
                class_name, prop_name, prop_desc, reason = prop_suggestion

                # 检查类是否存在
                class_def = self.system.get_class_definition(class_name)
                if not class_def:
                    logger.warning(
                        f"类 '{class_name}' 不存在，跳过属性建议: {prop_name}"
                    )
                    continue

                # 检查属性是否已存在
                if prop_name in class_def.property_names():
                    logger.debug(
                        f"属性 '{prop_name}' 已存在于类 '{class_name}' 中，跳过"
                    )
                    continue

                # 创建并添加新属性
                from ..models.entity import PropertyDefinition

                new_prop = PropertyDefinition(
                    name=prop_name,
                    required=False,  # LLM建议的属性默认为可选
                    value_required=False,
                    description=prop_desc,
                )

                # 添加到 System 中
                self.system.add_property(class_name, new_prop)
                added_count += 1

                logger.info(
                    f"✓ 为类 '{class_name}' 添加新属性 '{prop_name}': {prop_desc}"
                )
                logger.debug(f"  理由: {reason}")
            else:
                logger.warning(f"解析属性建议失败: {record[:100]}")

        if added_count > 0:
            logger.info(f"STEP 0 完成：共添加 {added_count} 个新属性到 System")
        else:
            logger.debug("STEP 0 完成：未添加新属性")

    def _parse_property_suggestion_record(self, record: str) -> Optional[tuple]:
        """
        解析单条属性建议记录

        格式: ("new_property"|<class_name>|<property_name>|<property_description>|<reason>)

        Returns:
            (class_name, property_name, property_description, reason) 或 None
        """
        try:
            # 移除括号和引号
            record = record.strip().strip("()").strip('"').strip("'")

            # 按分隔符分割
            parts = [
                p.strip().strip('"').strip("'")
                for p in record.split(self.tuple_delimiter)
            ]

            if len(parts) < 5:
                logger.warning(f"属性建议记录格式不正确，字段数不足: {len(parts)}")
                return None

            record_type = parts[0]
            if record_type != "new_property":
                logger.warning(f"记录类型不是 'new_property': {record_type}")
                return None

            class_name = parts[1]
            property_name = parts[2]
            property_description = parts[3]
            reason = parts[4]

            return (class_name, property_name, property_description, reason)

        except Exception as e:
            logger.error(f"解析属性建议记录时出错: {e}")
            logger.debug(f"问题记录: {record}")
            return None

    def _split_records(self, text: str) -> List[str]:
        """分割记录"""
        record_delimiter_pattern = self.record_delimiter
        if record_delimiter_pattern == "\n":
            records = [line.strip() for line in text.split("\n") if line.strip()]
        else:
            records = [
                r.strip() for r in text.split(record_delimiter_pattern) if r.strip()
            ]
        # 过滤掉标题行、注释行和空行，但保留包含实体格式的记录
        filtered_records = []
        for record in records:
            # 跳过空行
            if not record.strip():
                continue

            # 跳过注释行（以 # 开头）
            if record.strip().startswith("#"):
                logger.debug(f"过滤注释行: {record[:50]}")
                continue

            # 如果记录包含实体格式，即使包含标题行内容也要保留
            # 先检查是否包含实体格式
            contains_entity_format = (
                '("entity"' in record
                or '("class_property"' in record
                or '("relationship"' in record
                or '("new_property"' in record
            )

            if contains_entity_format:
                # 如果记录中包含换行符，可能是标题行和实体记录在同一分割结果中
                if "\n" in record:
                    # 按行分割，提取所有实体格式的行
                    lines = record.split("\n")
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        # 跳过注释行
                        if line.startswith("#"):
                            logger.debug(f"从混合行中过滤注释: {line[:50]}")
                            continue
                        # 提取实体格式的行
                        if (
                            line.startswith('("entity"')
                            or line.startswith('("class_property"')
                            or line.startswith('("relationship"')
                            or line.startswith('("new_property"')
                        ):
                            filtered_records.append(line)
                            logger.debug(f"从混合行中提取实体记录: {line[:80]}")
                else:
                    # 单行记录，直接保留
                    filtered_records.append(record)
                continue

            # 检查是否是纯标题行（不包含实体格式）
            is_title = (
                (record.startswith("STEP") and ":" in record)
                or record == "Entities:"
                or record == "Classes and Properties:"
                or record == "Relationships:"
                or record.startswith("STEP 0")
                or record.startswith("STEP 1")
                or record.startswith("STEP 2")
                or record.startswith("STEP 3")
            )

            # 如果是标题行且不包含实体格式，跳过
            if is_title:
                logger.debug(f"过滤标题行: {record[:50]}")
                continue

            # 其他情况保留
            filtered_records.append(record)

        logger.debug(
            f"分割得到 {len(records)} 条原始记录，过滤后 {len(filtered_records)} 条有效记录"
        )
        return filtered_records

    def _parse_response_legacy(
        self, response: str
    ) -> Tuple[List[Entity], List[Relationship]]:
        """传统解析方式（向后兼容）"""
        entities = []
        relationships = []
        records = self._split_records(response)

        for record in records:
            if record.startswith('("entity"'):
                entity = self._parse_entity(record)
                if entity:
                    entities.append(entity)
            elif record.startswith('("relationship"'):
                relationship = self._parse_relationship(record)
                if relationship:
                    relationships.append(relationship)

        return entities, relationships

    def _parse_entity_step1(self, record: str) -> Optional[Entity]:
        """
        解析第一步的实体记录（只有名称和描述）

        格式: ("entity"|ENTITY_NAME|DESCRIPTION)
        """
        try:
            record = record.strip().strip("()")
            parts = [p.strip().strip('"') for p in record.split(self.tuple_delimiter)]

            if len(parts) < 3 or parts[0] != "entity":
                return None

            name = parts[1]
            description = parts[2]

            # 创建实体（不添加类，类在第二步添加）
            # 创建一个临时实体，跳过验证
            from datetime import datetime

            entity = Entity.__new__(Entity)
            entity.name = name
            entity.description = description
            entity.classes = []
            entity.created_at = datetime.now()
            entity.updated_at = datetime.now()
            # 不调用 validate_against_system，因为还没有类

            logger.debug(f"解析实体成功: {name}")
            return entity
        except Exception as e:
            logger.error(f"解析实体失败: {record}, 错误: {e}", exc_info=True)
            return None

    def _parse_class_property(self, record: str, entities_dict: dict) -> None:
        """
        解析第二步的类属性记录

        格式: ("class_property"|ENTITY_NAME|CLASS_NAME|PROPERTY_NAME|PROPERTY_VALUE)
        如果属性值为NONE，表示该类没有该属性或值未提及
        """
        try:
            record = record.strip().strip("()")
            parts = [p.strip().strip('"') for p in record.split(self.tuple_delimiter)]

            if len(parts) < 5 or parts[0] != "class_property":
                return

            entity_name = parts[1]
            class_name = parts[2]
            property_name = parts[3]
            property_value = parts[4] if len(parts) > 4 else None

            # 获取实体
            entity = entities_dict.get(entity_name)
            if not entity:
                logger.warning(f"实体 '{entity_name}' 不存在，跳过类属性")
                return

            # 如果property_name是NONE，只添加类，不添加属性
            if property_name.upper() == "NONE" or property_value.upper() == "NONE":
                try:
                    entity.add_class(class_name)
                    logger.debug(f"为实体 {entity_name} 添加类: {class_name}")
                except ValueError as e:
                    logger.warning(
                        f"实体 {entity_name} 的类 '{class_name}' 未定义: {e}"
                    )
                return

            # 添加类（如果还没有）
            if not entity.has_class(class_name):
                try:
                    entity.add_class(class_name)
                except ValueError as e:
                    logger.warning(
                        f"实体 {entity_name} 的类 '{class_name}' 未定义: {e}"
                    )
                    return

            # 设置属性值
            try:
                entity.set_property_value(
                    class_name, property_name, value=property_value
                )
                logger.debug(
                    f"为实体 {entity_name} 的类 {class_name} 设置属性 {property_name} = {property_value}"
                )
            except ValueError as e:
                logger.warning(f"设置属性失败: {e}")

        except Exception as e:
            logger.error(f"解析类属性失败: {record}, 错误: {e}", exc_info=True)

    def _parse_entity(self, record: str) -> Optional[Entity]:
        """
        解析实体记录

        格式: ("entity"|ENTITY_NAME|CLASS_NAME|DESCRIPTION)
        或: ("entity"|ENTITY_NAME|CLASS_NAME1,CLASS_NAME2,...|DESCRIPTION)  # 支持多个类
        """
        try:
            # 移除括号和引号
            record = record.strip().strip("()")

            # 分割字段
            parts = [p.strip().strip('"') for p in record.split(self.tuple_delimiter)]

            if len(parts) < 4 or parts[0] != "entity":
                return None

            name = parts[1]
            class_names_str = parts[2]  # 可能是单个类名或多个类名（逗号分隔）
            description = parts[3]

            # 解析类名（支持逗号分隔的多个类）
            class_names = [c.strip() for c in class_names_str.split(",") if c.strip()]

            # 创建实体
            entity = Entity(
                name=name,
                description=description,
            )

            # 为每个类添加类实例
            for class_name in class_names:
                try:
                    class_instance = entity.add_class(class_name, system=self.system)
                    logger.debug(f"为实体 {name} 添加类: {class_name}")
                except ValueError as e:
                    logger.warning(f"实体 {name} 的类 '{class_name}' 未定义，跳过: {e}")

            logger.debug(f"解析实体成功: {name} (类: {class_names})")
            return entity
        except Exception as e:
            logger.error(f"解析实体失败: {record}, 错误: {e}", exc_info=True)
            return None

    def _parse_relationship(self, record: str) -> Optional[Relationship]:
        """
        解析关系记录

        格式: ("relationship"|source|target|DESCRIPTION|COUNT|REFER_LIST|SEMANTIC_TIME)
        REFER_LIST: 逗号分隔的实体列表（如"微信:交流平台,支付宝:支付工具"）或"NONE"
        SEMANTIC_TIME: ISO 8601格式的时间（如"2026-01-10T10:30:00"）或"NONE"
        """
        try:
            # 移除括号和引号
            record = record.strip().strip("()")

            # 分割字段
            parts = [p.strip().strip('"') for p in record.split(self.tuple_delimiter)]

            if len(parts) < 5 or parts[0] != "relationship":
                return None

            source = parts[1]
            target = parts[2]
            description = parts[3]
            count = int(parts[4])

            # 解析 refer 字段（新增，向后兼容）
            refer = []
            if len(parts) >= 6:
                refer_str = parts[5].strip()
                if refer_str and refer_str.upper() != "NONE":
                    # 处理中文逗号和英文逗号
                    refer_str = refer_str.replace("，", ",")
                    # 按逗号分割，去除空格
                    refer = [r.strip() for r in refer_str.split(",") if r.strip()]

            # 解析 semantic_time 字段（新增，向后兼容）
            semantic_times = []
            if len(parts) >= 7:
                semantic_time_str = parts[6].strip()
                if semantic_time_str and semantic_time_str.upper() != "NONE":
                    # 如果提供了有效的时间，添加到列表
                    semantic_times.append(semantic_time_str)

            relationship = Relationship(
                source=source,
                target=target,
                description=description,
                count=count,
                refer=refer,  # 添加 refer 字段
                semantic_times=semantic_times,  # 添加 semantic_times 字段
            )

            if refer:
                logger.debug(
                    f"解析关系成功: {source} -> {target} (次数: {count}, refer: {refer})"
                )
            else:
                logger.debug(f"解析关系成功: {source} -> {target} (次数: {count})")
            return relationship
        except Exception as e:
            logger.error(f"解析关系失败: {record}, 错误: {e}", exc_info=True)
            return None
