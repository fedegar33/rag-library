# Propuesta de cobertura de evaluaciones — 2026-10-24

> Follow-up: the agreed first implementation is documented in
> [Agent behavior evals](agent-behavior-evals.md): 14 synthetic single-turn cases.
> Conversation evaluation remains deferred.

Investigación de documentación oficial y del código instalado de **DeepEval
4.3.0**. Las métricas propuestas están disponibles en esa versión. No se
ejecutaron jueces LLM ni evaluaciones pagas; únicamente inspección y tres
comprobaciones con un modelo de prueba que falla si se intenta generar texto.
Este documento propone cambios; no modifica el runner ni los datasets.

## Qué cubrimos hoy y qué queda fuera

El runner actual combina Answer Correctness (G-Eval) y Faithfulness, con tres
diagnósticos opcionales de retrieval. Es apropiado para preguntas sobre contenido,
pero no cubre directamente decisiones del agente ni conversaciones:

- `build_test_case` guarda las ejecuciones en `metadata["tool_calls"]`, sin llenar
  los campos nativos `tools_called` y `expected_tools` de DeepEval.
- `score_results` rechaza respuestas sin pasajes recuperados. Una consulta correcta
  de catálogo, una aclaración o un agradecimiento no pueden pasar por ese scorer.
- `run_evaluation` genera preguntas independientes mediante `run_agent`. No recorre
  la conversión de historial ni la sliding window del chat.
- El dataset actual exige referencias de libros no vacías. Casos de biblioteca
  completa o vacía necesitan expresar su alcance sin modificar las reglas del
  dataset RAG existente.

Evidencia: [scorer](../src/rag_library/deepeval_evaluation.py),
[generación](../src/rag_library/evaluation.py),
[historial](../src/rag_library/agent/history.py).

## Métricas que priorizaría

| Métrica | Pregunta que responde | Aplicación en este proyecto |
| --- | --- | --- |
| [ToolCorrectnessMetric](https://deepeval.com/docs/metrics-tool-correctness) | ¿Se llamaron las tools esperadas? | Catálogo → `list_available_books`; contenido → `answer_book_question`; agradecimiento → ninguna. |
| [ArgumentCorrectnessMetric](https://deepeval.com/docs/metrics-argument-correctness) | ¿Los argumentos tienen sentido respecto de la solicitud? | La pregunta enviada al retriever debe resolver referencias como “él”, sin introducir hechos o términos adivinados. |
| [GEval / ConversationalGEval](https://deepeval.com/docs/metrics-llm-evals) | ¿Cumple una regla semántica específica del producto? | Resolver “el primer libro” desde el resultado de catálogo, responder seguimientos y pedir aclaración si falta el referente. Usar criterios separados y pasos explícitos. |
| [PromptAlignmentMetric](https://deepeval.com/docs/metrics-prompt-alignment) | ¿La respuesta sigue las instrucciones de presentación? | Introducción breve para cards y ausencia de un segundo listado redundante en texto. |

Tool Correctness compara nombres por defecto. Permite comparar parámetros,
resultados y orden; sin `available_tools`, la comparación no requiere un juez.
Para las rutas simples usaría `should_exact_match=True`, sin igualdad literal de
la pregunta reformulada. Argument Correctness aporta el juicio semántico sobre
esa pregunta, pero necesita recibir su contexto conversacional para juzgar un
seguimiento; evaluar únicamente “¿y dónde trabaja?” sería insuficiente.

Prompt Alignment evalúa la respuesta, no el render visual. Tampoco comprueba por
sí solo que el anuncio ocurrió antes de la tool: ese orden requiere eventos SSE
o una trayectoria instrumentada. Para criterios que incluyen datos estructurados,
G-Eval debe recibir `TOOLS_CALLED`, además de los parámetros de texto pertinentes.

## Comprobaciones offline y dos trampas de interpretación

Resultados reproducidos con el código instalado, sin generar texto con un juez:

| Caso | Configuración | Score observado |
| --- | --- | --- |
| Se esperaba catálogo, se llamó catálogo y además retrieval | Tool Correctness por defecto | 1.0 |
| Mismo caso | Tool Correctness con exact match | 0.0 |
| No se ejecutó ninguna tool | Argument Correctness | 1.0 |

Por lo tanto, una buena puntuación de argumentos no prueba que se haya llamado
una tool requerida; y la configuración por defecto de Tool Correctness puede no
penalizar llamadas adicionales. No usaría una sola métrica como indicador general
de funcionamiento del agente.

## Métricas útiles para una segunda etapa

- [TurnRelevancyMetric](https://deepeval.com/docs/metrics-turn-relevancy): detecta
  respuestas que pierden el hilo. La relevancia no demuestra exactitud factual.
  Su `window_size` corresponde al juez, no al presupuesto de tokens de nuestra app.
- [KnowledgeRetentionMetric](https://deepeval.com/docs/metrics-knowledge-retention):
  verifica retención de hechos aportados por el **usuario**. No sustituye una eval
  sobre resultados históricos de tools: en modo LLM, extrae conocimiento de los
  mensajes de usuario y busca pérdidas en las respuestas posteriores.
- [ToolUseMetric](https://deepeval.com/docs/metrics-tool-use): combina selección de
  tools y argumentos a través de una conversación, con descripción de las tools
  disponibles. Puede ser útil después de establecer los diagnósticos separados.
- [ConversationCompletenessMetric](https://deepeval.com/docs/metrics-conversation-completeness):
  mide satisfacción de necesidades a lo largo del diálogo. La usaría como señal
  global secundaria, evitando que esconda qué turno falló.
- [TaskCompletionMetric](https://deepeval.com/docs/metrics-task-completion) y
  [StepEfficiencyMetric](https://deepeval.com/docs/metrics-step-efficiency): más
  apropiadas cuando evaluemos trayectorias y tareas de varios pasos. La
  documentación de Task Completion recomienda traces de DeepEval. En 4.3.0 todavía
  existe un camino sin trace marcado para futura deprecación; no basaría una
  integración nueva en él. Tener tracing en LangSmith no entrega automáticamente
  esos traces al scorer actual.

## Casos iniciales propuestos

Separaría la suite RAG existente de dos suites nuevas:

1. **Comportamiento del agente:** aproximadamente 12 casos cortos de catálogo,
   contenido, biblioteca vacía, metadatos ausentes y respuestas sin tools.
   Variar adjuntos explícitos y biblioteca completa. Una consulta de catálogo
   siempre debe consultar todo el catálogo aunque existan adjuntos.
2. **Conversación:** aproximadamente 6 diálogos de 2–4 preguntas: catálogo → autor
   del primer libro; entidad → seguimiento con pronombre; corrección del usuario;
   cambio de selección A → B; referente dentro de la ventana; referente fuera de
   la ventana que requiere aclaración.

Estas cantidades son un punto de partida propuesto, no nuevos casos ya curados.
Las expectativas factuales deben revisarse contra EPUB/fixtures, igual que en RAG.
No introduciría aún un simulador de usuarios: diálogos guionados facilitan atribuir
regresiones al agente.

Para sliding window distinguiría memoria disponible de memoria intencionalmente
descartada. Medir retención sobre todo el transcript sin registrar qué recibió
el modelo podría castigar un comportamiento esperado. Una aclaración tras perder
un referente debe poder aprobar; inventarlo debe fallar.

## Integración mínima propuesta

- Adaptar registros reales a `ToolCall(name=..., input_parameters=..., output=...)`.
  Mantener los registros originales y las expectativas congeladas al generar.
- Elegir métricas por tipo de caso. Catálogo y conversación no deben exigir
  `retrieval_context` ni recibir Faithfulness sobre una introducción sin pasajes.
  Mantener sin cambios las reglas de Answer Correctness/Faithfulness del RAG actual.
- Para conversación, ejecutar el mismo camino de mensajes y sliding window del
  chat. Guardar por turno la pregunta, respuesta, tools, contexto efectivo,
  selección de libros y configuración de retrieval/modelo.
- Adaptar a `ConversationalTestCase(turns=...)`. Sus `Turn` aceptan usuario y
  asistente: las ejecuciones se adjuntan en `tools_called` del turno del asistente,
  con sus outputs; no se copia directamente nuestra lista HTTP con roles `tool`.
- Mantener generación y scoring separados. Revaluar archivos congelados sin
  volver a consultar catálogo, retrieval o modelos de respuesta.
- Comenzar métricas LLM en score-only (`threshold=None`), con juez explícito y
  pasos/rúbrica revisados sobre ejemplos buenos y malos. Definir umbrales después
  de comprobar acuerdo humano; no extender automáticamente el 0.7 del RAG.

## Qué comprobaría sin un juez

Los IDs de las fuentes deben pertenecer al alcance actual; la selección no debe
ampliarse por historial; las cards deben cumplir su esquema; los pares de tools
deben sobrevivir enteros al recorte; y las llamadas históricas no deben repetirse.
Son aserciones deterministas sobre ejecuciones y contratos, complementarias a
DeepEval. Ya existen pruebas offline para parte de estas reglas.

Contaría también llamadas por turno, latencia y tokens como diagnósticos. La
apariencia de las cards y la interacción del drawer necesitan pruebas de UI;
un score de texto no las verifica.
