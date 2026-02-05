"""
PDF генератор для дайджестов.
Reflexio v2.1 — Surpass Smart Noter Sprint
"""
from pathlib import Path
from datetime import date, datetime
from typing import Dict, List, Optional
import io

from src.utils.logging import get_logger

logger = get_logger("digest.pdf")

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("reportlab not available. Install: pip install reportlab")


class PDFGenerator:
    """Генератор PDF дайджестов."""
    
    def __init__(self):
        """Инициализация генератора."""
        if not REPORTLAB_AVAILABLE:
            raise ImportError("reportlab package required. Install: pip install reportlab")
        
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Настройка кастомных стилей."""
        # Заголовок
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1a1a1a'),
            spaceAfter=30,
            alignment=1,  # Center
        ))
        
        # Подзаголовок
        self.styles.add(ParagraphStyle(
            name='CustomSubtitle',
            parent=self.styles['Normal'],
            fontSize=12,
            textColor=colors.HexColor('#666666'),
            spaceAfter=20,
            alignment=1,  # Center
        ))
        
        # Заголовок секции
        self.styles.add(ParagraphStyle(
            name='SectionTitle',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=12,
            spaceBefore=20,
        ))
        
        # Метрика
        self.styles.add(ParagraphStyle(
            name='Metric',
            parent=self.styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#34495e'),
            leftIndent=20,
        ))
    
    def generate(
        self,
        target_date: date,
        transcriptions: List[Dict],
        facts: List[Dict],
        metrics: Dict,
        output_path: Optional[Path] = None,
    ) -> Path:
        """
        Генерирует PDF дайджест.
        
        Args:
            target_date: Дата дайджеста
            transcriptions: Список транскрипций
            facts: Список фактов
            metrics: Метрики дня
            output_path: Путь для сохранения (если None, создаётся автоматически)
            
        Returns:
            Путь к созданному PDF файлу
        """
        if output_path is None:
            output_dir = Path("digests")
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / f"digest_{target_date.isoformat()}.pdf"
        
        # Создаём PDF документ
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72,
        )
        
        # Собираем контент
        story = []
        
        # Титульная страница
        story.append(Paragraph("Reflexio 24/7", self.styles['CustomTitle']))
        story.append(Spacer(1, 0.2 * inch))
        story.append(Paragraph(
            f"Дневной дайджест — {target_date.strftime('%d %B %Y')}",
            self.styles['CustomSubtitle']
        ))
        story.append(Paragraph(
            f"Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            self.styles['CustomSubtitle']
        ))
        story.append(PageBreak())
        
        # Метрики дня
        story.append(Paragraph("📊 Метрики дня", self.styles['SectionTitle']))
        
        metrics_data = [
            ['Метрика', 'Значение'],
            ['Транскрипций', str(metrics.get('transcriptions_count', 0))],
            ['Фактов извлечено', str(metrics.get('facts_count', 0))],
            ['Общая длительность', f"{metrics.get('total_duration_minutes', 0):.1f} мин"],
            ['Слов обработано', str(metrics.get('total_words', 0))],
            ['Информационная плотность', f"{metrics.get('information_density_score', 0):.1f}/100"],
        ]
        
        metrics_table = Table(metrics_data, colWidths=[3 * inch, 2 * inch])
        metrics_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        
        story.append(metrics_table)
        story.append(Spacer(1, 0.3 * inch))
        
        # Факты
        if facts:
            story.append(Paragraph("📝 Извлечённые факты", self.styles['SectionTitle']))
            
            for i, fact in enumerate(facts, 1):
                fact_type = fact.get('type', 'fact').upper()
                fact_text = fact.get('text', '')
                timestamp = fact.get('timestamp', '')[:16] if fact.get('timestamp') else ''
                
                fact_para = f"<b>{i}. [{fact_type}]</b> {fact_text}"
                if timestamp:
                    fact_para += f"<br/><i>{timestamp}</i>"
                
                story.append(Paragraph(fact_para, self.styles['Normal']))
                story.append(Spacer(1, 0.1 * inch))
        
        # Транскрипции (если есть место)
        if transcriptions and len(transcriptions) <= 5:  # Ограничиваем для PDF
            story.append(PageBreak())
            story.append(Paragraph("🎤 Транскрипции", self.styles['SectionTitle']))
            
            for i, trans in enumerate(transcriptions, 1):
                timestamp = trans.get('created_at', '')[:16] if trans.get('created_at') else ''
                language = trans.get('language', 'unknown')
                duration = trans.get('duration', 0) or 0
                
                header = f"<b>Транскрипция #{i}</b> — {timestamp} | {language} | {duration:.1f}s"
                story.append(Paragraph(header, self.styles['Normal']))
                story.append(Spacer(1, 0.05 * inch))
                
                text = trans.get('text', '')
                # Ограничиваем длину текста для PDF
                if len(text) > 500:
                    text = text[:500] + "..."
                
                story.append(Paragraph(text, self.styles['Normal']))
                story.append(Spacer(1, 0.2 * inch))
        
        # Подвал
        story.append(Spacer(1, 0.5 * inch))
        story.append(Paragraph(
            "<i>Reflexio 24/7 — автоматический дневной дайджест</i>",
            self.styles['CustomSubtitle']
        ))
        
        # Собираем PDF
        doc.build(story)
        
        logger.info("pdf_generated", path=str(output_path), size_bytes=output_path.stat().st_size)
        
        return output_path





