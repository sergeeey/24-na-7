"""
Reflexio Knowledge Graph — визуализация взаимосвязей утверждений.

Базовая структура для создания графа знаний из OSINT результатов.
"""
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.osint.schemas import ValidatedClaim

try:
    from src.utils.logging import setup_logging, get_logger
    setup_logging()
    logger = get_logger("osint.kgraph")
except Exception:
    import logging
    logger = logging.getLogger("osint.kgraph")


class KnowledgeGraph:
    """Граф знаний из OSINT утверждений."""
    
    def __init__(self):
        self.nodes: Dict[str, Dict[str, Any]] = {}  # entity_id -> entity_data
        self.edges: List[Dict[str, Any]] = []  # [{source, target, relation, weight}]
        self.claims: List[ValidatedClaim] = []
    
    def add_claim(self, claim: ValidatedClaim):
        """Добавляет утверждение в граф."""
        self.claims.append(claim)
        
        # Извлекаем сущности из текста утверждения
        entities = self._extract_entities(claim.claim.text)
        
        # Создаём узлы для сущностей
        for entity in entities:
            entity_id = self._normalize_entity(entity)
            
            if entity_id not in self.nodes:
                self.nodes[entity_id] = {
                    "id": entity_id,
                    "label": entity,
                    "type": self._guess_entity_type(entity),
                    "claims_count": 0,
                    "confidence_sum": 0.0,
                }
            
            # Обновляем статистику
            self.nodes[entity_id]["claims_count"] += 1
            self.nodes[entity_id]["confidence_sum"] += claim.calibrated_confidence
        
        # Создаём связи между сущностями в одном утверждении
        if len(entities) > 1:
            for i, source in enumerate(entities):
                for target in entities[i + 1:]:
                    self._add_edge(source, target, claim)
    
    def _extract_entities(self, text: str) -> List[str]:
        """
        Извлекает сущности из текста.
        
        TODO: Заменить на более продвинутый NER (spaCy, NLTK и т.д.)
        """
        # Простая эвристика: слова с заглавной буквы и числа
        import re
        
        # Компании (Capitalized words, возможно с Ltd, Inc и т.д.)
        companies = re.findall(r'\b[A-Z][a-zA-Z]+(?:\s+(?:Ltd|Inc|Corp|LLC|AG|SA))?\b', text)
        
        # Числа с валютой (суммы)
        amounts = re.findall(r'\$?\s*\d+(?:[.,]\d+)*\s*(?:млн|million|billion|млрд)?', text, re.IGNORECASE)
        
        # Даты
        dates = re.findall(r'\d{4}-\d{2}-\d{2}|\d{1,2}\s+\w+\s+\d{4}', text)
        
        entities = list(set(companies + amounts + dates))
        
        return entities
    
    def _normalize_entity(self, entity: str) -> str:
        """Нормализует имя сущности для использования как ID."""
        return entity.lower().strip()
    
    def _guess_entity_type(self, entity: str) -> str:
        """Определяет тип сущности."""
        entity_lower = entity.lower()
        
        if any(x in entity_lower for x in ["ltd", "inc", "corp", "llc", "ag", "sa"]):
            return "company"
        elif "$" in entity or any(x in entity_lower for x in ["млн", "million", "billion"]):
            return "amount"
        elif "-" in entity or any(x in entity_lower for x in ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]):
            return "date"
        else:
            return "entity"
    
    def _add_edge(self, source: str, target: str, claim: ValidatedClaim):
        """Добавляет связь между сущностями."""
        source_id = self._normalize_entity(source)
        target_id = self._normalize_entity(target)
        
        # Проверяем, есть ли уже такая связь
        existing = next(
            (e for e in self.edges if 
             (e["source"] == source_id and e["target"] == target_id) or
             (e["source"] == target_id and e["target"] == source_id)),
            None
        )
        
        if existing:
            # Обновляем вес (увеличиваем количество упоминаний)
            existing["weight"] += 1
            existing["confidence_sum"] += claim.calibrated_confidence
            existing["claims"].append(claim.claim.text[:100])
        else:
            # Создаём новую связь
            self.edges.append({
                "source": source_id,
                "target": target_id,
                "relation": "related_to",
                "weight": 1,
                "confidence_sum": claim.calibrated_confidence,
                "claims": [claim.claim.text[:100]],
            })
    
    def to_cytoscape(self) -> Dict[str, Any]:
        """
        Конвертирует граф в формат Cytoscape.js для визуализации.
        
        Returns:
            Словарь с nodes и edges для Cytoscape
        """
        nodes = [
            {
                "data": {
                    "id": node_id,
                    "label": node["label"],
                    "type": node["type"],
                    "size": node["claims_count"],
                    "confidence": node["confidence_sum"] / node["claims_count"] if node["claims_count"] > 0 else 0,
                }
            }
            for node_id, node in self.nodes.items()
        ]
        
        edges = [
            {
                "data": {
                    "id": f"{edge['source']}-{edge['target']}",
                    "source": edge["source"],
                    "target": edge["target"],
                    "label": edge["relation"],
                    "weight": edge["weight"],
                    "confidence": edge["confidence_sum"] / edge["weight"] if edge["weight"] > 0 else 0,
                }
            }
            for edge in self.edges
        ]
        
        return {"nodes": nodes, "edges": edges}
    
    def to_graphml(self) -> str:
        """
        Экспортирует граф в GraphML формат.
        
        Returns:
            XML строка в формате GraphML
        """
        xml_parts = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
            '  <key id="type" for="node" attr.name="type" attr.type="string"/>',
            '  <key id="confidence" for="node" attr.name="confidence" attr.type="double"/>',
            '  <key id="weight" for="edge" attr.name="weight" attr.type="int"/>',
            '  <graph id="knowledge_graph" edgedefault="undirected">',
        ]
        
        # Узлы
        for node_id, node in self.nodes.items():
            avg_confidence = node["confidence_sum"] / node["claims_count"] if node["claims_count"] > 0 else 0
            xml_parts.append(f'    <node id="{node_id}">')
            xml_parts.append(f'      <data key="type">{node["type"]}</data>')
            xml_parts.append(f'      <data key="confidence">{avg_confidence:.2f}</data>')
            xml_parts.append(f'    </node>')
        
        # Связи
        for idx, edge in enumerate(self.edges):
            edge_id = f"e{idx}"
            xml_parts.append(f'    <edge id="{edge_id}" source="{edge["source"]}" target="{edge["target"]}">')
            xml_parts.append(f'      <data key="weight">{edge["weight"]}</data>')
            xml_parts.append(f'    </edge>')
        
        xml_parts.extend([
            '  </graph>',
            '</graphml>',
        ])
        
        return '\n'.join(xml_parts)
    
    def export_json(self, output_path: Path):
        """Экспортирует граф в JSON."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {
            "nodes": [
                {
                    **node,
                    "avg_confidence": node["confidence_sum"] / node["claims_count"] if node["claims_count"] > 0 else 0,
                }
                for node_id, node in self.nodes.items()
            ],
            "edges": [
                {
                    **edge,
                    "avg_confidence": edge["confidence_sum"] / edge["weight"] if edge["weight"] > 0 else 0,
                }
                for edge in self.edges
            ],
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info("knowledge_graph_exported", path=str(output_path), nodes=len(data["nodes"]), edges=len(data["edges"]))


def build_knowledge_graph_from_results(results_dir: Path = Path(".cursor/osint/results")) -> KnowledgeGraph:
    """
    Строит граф знаний из результатов миссий.
    
    Args:
        results_dir: Директория с результатами миссий
        
    Returns:
        KnowledgeGraph объект
    """
    graph = KnowledgeGraph()
    
    if not results_dir.exists():
        logger.warning("results_dir_not_found", path=str(results_dir))
        return graph
    
    # Загружаем все результаты
    for result_file in results_dir.glob("*_result_*.json"):
        try:
            with open(result_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Извлекаем утверждения
            claims_data = data.get("claims", [])
            
            for claim_data in claims_data:
                # Конвертируем в ValidatedClaim
                from src.osint.schemas import Claim, ValidatedClaim
                
                claim_obj = Claim(**claim_data["claim"])
                validated_claim = ValidatedClaim(
                    claim=claim_obj,
                    validation_status=claim_data["validation_status"],
                    critic_confidence=claim_data["critic_confidence"],
                    calibrated_confidence=claim_data["calibrated_confidence"],
                    evidence=claim_data.get("evidence", []),
                    validated_at=claim_data.get("validated_at", ""),
                )
                
                graph.add_claim(validated_claim)
            
        except Exception as e:
            logger.warning("result_load_failed", file=str(result_file), error=str(e))
    
    logger.info(
        "knowledge_graph_built",
        nodes=len(graph.nodes),
        edges=len(graph.edges),
        claims=len(graph.claims),
    )
    
    return graph


def main():
    """CLI для Knowledge Graph."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Reflexio Knowledge Graph")
    parser.add_argument(
        "--build",
        action="store_true",
        help="Построить граф из результатов миссий",
    )
    parser.add_argument(
        "--export",
        type=Path,
        help="Экспортировать граф (json, graphml, cytoscape)",
    )
    parser.add_argument(
        "--format",
        choices=["json", "graphml", "cytoscape"],
        default="json",
        help="Формат экспорта",
    )
    
    args = parser.parse_args()
    
    if args.build:
        graph = build_knowledge_graph_from_results()
        
        print("\n" + "=" * 70)
        print("Knowledge Graph Built")
        print("=" * 70)
        print(f"Nodes: {len(graph.nodes)}")
        print(f"Edges: {len(graph.edges)}")
        print(f"Claims: {len(graph.claims)}")
        
        if args.export:
            if args.format == "json":
                graph.export_json(args.export)
            elif args.format == "graphml":
                args.export.write_text(graph.to_graphml(), encoding="utf-8")
            elif args.format == "cytoscape":
                data = graph.to_cytoscape()
                args.export.parent.mkdir(parents=True, exist_ok=True)
                with open(args.export, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"\n✅ Exported to: {args.export}")
        
        print("=" * 70 + "\n")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())













