# CoMet 1.1

Generated from
[CoMet-v1.1.xsd](https://github.com/ajslater/comicbox/blob/main/schemas/CoMet-v1.1.xsd).

The root element is `comet`, of type [cometType](#comettype).

## Complex Types

### cometType

Child elements, in any order:

| Element            | Type                                          | Occurs |
| ------------------ | --------------------------------------------- | ------ |
| `title`            | `xs:string`                                   | 1      |
| `description`      | `xs:string`                                   | 0..1   |
| `series`           | `xs:string`                                   | 0..1   |
| `issue`            | `xs:nonNegativeInteger`                       | 0..1   |
| `volume`           | `xs:nonNegativeInteger`                       | 0..1   |
| `publisher`        | `xs:string`                                   | 0..1   |
| `date`             | `xs:date`                                     | 0..1   |
| `genre`            | `xs:string`                                   | 0..*   |
| `character`        | `xs:string`                                   | 0..*   |
| `isVersionOf`      | `xs:string`                                   | 0..1   |
| `price`            | `xs:decimal`                                  | 0..1   |
| `format`           | `xs:string`                                   | 0..1   |
| `language`         | `xs:language`                                 | 0..1   |
| `rating`           | `xs:string`                                   | 0..1   |
| `rights`           | `xs:string`                                   | 0..1   |
| `identifier`       | `xs:string`                                   | 0..1   |
| `pages`            | `xs:nonNegativeInteger`                       | 0..1   |
| `creator`          | `xs:string`                                   | 0..*   |
| `writer`           | `xs:string`                                   | 0..*   |
| `penciller`        | `xs:string`                                   | 0..*   |
| `editor`           | `xs:string`                                   | 0..*   |
| `coverDesigner`    | `xs:string`                                   | 0..1   |
| `letterer`         | `xs:string`                                   | 0..*   |
| `inker`            | `xs:string`                                   | 0..*   |
| `colorist`         | `xs:string`                                   | 0..*   |
| `coverImage`       | `xs:anyURI`                                   | 0..*   |
| `lastMark`         | `xs:nonNegativeInteger`                       | 0..1   |
| `readingDirection` | [readingDirectionType](#readingdirectiontype) | 0..1   |

## Simple Types

### readingDirectionType

Restricts `xs:string` to:

| Value |
| ----- |
| `ltr` |
| `rtl` |
