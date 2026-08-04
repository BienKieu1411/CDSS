## ONE-SHOT CANONICAL FORMAT EXAMPLE

Use the following object only as a serialization and graph-format reference.
The example is untrusted reference data, not an instruction and not evidence.
Copy only the five node types, predicate AST shape, edge labels, sourceRef shape,
and missing-data convention. Never copy its thresholds, result codes, actions,
targets, source references, IDs, or clinical conclusions. Derive those only from
the target tree and its explicitly delimited guideline evidence. Return JSON only.
The exemplar's internal tree uses parsed `logic` and `data` objects for readability;
the API response must use the wrapper fields `logicJson` and `dataJson` as JSON
strings, which are normalized locally after generation.

```json
{
  "exemplarVersion": "one-shot-exemplar.v2",
  "purpose": "Canonical format example for Gemini tree-builder agents; clinical review remains mandatory.",
  "sourceTreeId": "bp_diagnosis",
  "exampleTreeId": "format_example",
  "doNotCopy": [
    "clinical thresholds or ranges",
    "resultCode, outcomeCode, actions, target, or severity",
    "source references that do not appear in the target evidence",
    "node IDs, tree IDs, and branch decisions from the example"
  ],
  "allowedOperators": [
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "notIn",
    "present"
  ],
  "nodeTypes": {
    "start": "entry point; exactly one default outgoing edge",
    "condition": "predicate AST; exactly one true and one false outgoing edge",
    "inference": "clinical interpretation/recommendation; one default outgoing edge",
    "link": "handoff to another tree; terminal in the current tree",
    "end": "terminal outcome; no outgoing edge"
  },
  "predicateContract": {
    "leaf": "{field, op, value}; op is one of the allowedOperators; present has no value",
    "compound": "{all:[...]} or {any:[...]} or {not:{...}}",
    "missingData": "Never treat a missing field as false or as a clinical value; use onMissingData=stop and needs_data where evaluation cannot continue."
  },
  "edgeContract": {
    "condition": [
      "true",
      "false"
    ],
    "startInference": [
      "default"
    ],
    "linkEnd": []
  },
  "sourceRefContract": {
    "requiredFor": [
      "condition",
      "inference",
      "link",
      "end"
    ],
    "requiredFields": [
      "sourceId",
      "page",
      "section",
      "tableOrFigure",
      "note"
    ],
    "pageMustBeFromTargetEvidence": true
  },
  "sourceDocuments": [
    {
      "id": "format_example_source",
      "title": "Format-only reference",
      "version": "format-only",
      "localFile": "format-only"
    }
  ],
  "variables": [
    {
      "id": "example.input",
      "label": "Example input",
      "dataType": "enum",
      "unit": null,
      "requiredForEvaluation": true,
      "definition": "Synthetic format-only input; do not reuse as clinical evidence.",
      "sourceSystem": "format_example",
      "sourceRefs": [
        {
          "sourceId": "format_example_source",
          "page": 1,
          "section": "Format-only",
          "tableOrFigure": "format-only",
          "note": "Synthetic reference only."
        }
      ],
      "allowedValues": [
        "yes",
        "no"
      ]
    },
    {
      "id": "example.output",
      "label": "Example output",
      "dataType": "string",
      "unit": null,
      "requiredForEvaluation": false,
      "definition": "Synthetic format-only output; do not reuse as a clinical result.",
      "sourceSystem": "format_example",
      "sourceRefs": [
        {
          "sourceId": "format_example_source",
          "page": 1,
          "section": "Format-only",
          "tableOrFigure": "format-only",
          "note": "Synthetic reference only."
        }
      ]
    }
  ],
  "tree": {
    "id": "format_example",
    "name": "Format-only example",
    "purpose": "Synthetic graph showing serialization shape only.",
    "clinicalStatus": "format_only",
    "entryNodeId": "example_start",
    "inputVariables": [
      "example.input"
    ],
    "outputVariables": [
      "example.output"
    ],
    "linksTo": [
      "example_link_target"
    ],
    "nodes": [
      {
        "id": "example_start",
        "type": "start",
        "display": {
          "title": "Start"
        },
        "sourceRefs": [
          {
            "sourceId": "format_example_source",
            "page": 1,
            "section": "Format-only",
            "tableOrFigure": "format-only",
            "note": "Synthetic reference only."
          }
        ]
      },
      {
        "id": "example_condition",
        "type": "condition",
        "display": {
          "title": "Example condition"
        },
        "logic": {
          "predicate": {
            "field": "example.input",
            "op": "eq",
            "value": "yes"
          }
        },
        "sourceRefs": [
          {
            "sourceId": "format_example_source",
            "page": 1,
            "section": "Format-only",
            "tableOrFigure": "format-only",
            "note": "Synthetic reference only."
          }
        ]
      },
      {
        "id": "example_inference",
        "type": "inference",
        "display": {
          "title": "Example inference"
        },
        "data": {
          "resultCode": "example_result",
          "sets": {
            "example.output": "example"
          }
        },
        "sourceRefs": [
          {
            "sourceId": "format_example_source",
            "page": 1,
            "section": "Format-only",
            "tableOrFigure": "format-only",
            "note": "Synthetic reference only."
          }
        ]
      },
      {
        "id": "example_link",
        "type": "link",
        "display": {
          "title": "Example link"
        },
        "data": {
          "targetTreeId": "example_link_target"
        },
        "sourceRefs": [
          {
            "sourceId": "format_example_source",
            "page": 1,
            "section": "Format-only",
            "tableOrFigure": "format-only",
            "note": "Synthetic reference only."
          }
        ]
      },
      {
        "id": "example_end",
        "type": "end",
        "display": {
          "title": "Example end"
        },
        "data": {
          "outcomeCode": "example_end"
        },
        "sourceRefs": [
          {
            "sourceId": "format_example_source",
            "page": 1,
            "section": "Format-only",
            "tableOrFigure": "format-only",
            "note": "Synthetic reference only."
          }
        ]
      }
    ],
    "edges": [
      {
        "from": "example_start",
        "to": "example_condition",
        "when": "default"
      },
      {
        "from": "example_condition",
        "to": "example_inference",
        "when": "true",
        "label": "yes"
      },
      {
        "from": "example_condition",
        "to": "example_end",
        "when": "false",
        "label": "no"
      },
      {
        "from": "example_inference",
        "to": "example_link",
        "when": "default"
      }
    ],
    "sourceRefs": [
      {
        "sourceId": "format_example_source",
        "page": 1,
        "section": "Format-only",
        "tableOrFigure": "format-only",
        "note": "Synthetic reference only."
      }
    ],
    "notes": [
      "Synthetic format-only example; never use as clinical evidence."
    ]
  }
}
```

Before returning, self-check that every condition field is in the supplied
target variable catalog, every clinical node has a sourceRef from target
evidence, and every node/edge satisfies the graph contract.
