
## table 0

| Hardware Features | Ampere and TU GPUs | Ada GPUs | Blackwell GPUs | Jetson Thor |
| Baseline main and high profile: Capability to encode YUV 420 sequence | Y | Y | Y | Y |
| High10 profile: Support for encoding 10-bit content. | N | N | Y | N |
| 4:2:2 encoding | N | N | Y | N |
| 4:4:4 encoding (only CAVLC) | Y | Y | Y | Y |
| Lossless encoding | Y | Y | Y | Y |
| Motion estimation (ME) only mode: Capability to provide macro-block level motion vectors and intra or inter modes. | Y | Y | Y | Y |
| Field encoding | N | N | Y | N |
| Weighted prediction | Y | Y | Y | Y |
| Encoding support ARGB content | Y | Y | Y | Y |
| Multiple reference frames : Capability to use different reference frames | Y | Y | Y | Y |

## table 1

| Hardware Features | Ampere and TU GPUs | Ada GPUs | Blackwell GPUs | Jetson Thor |
| Main profile: Capability to encode YUV 4:2:0 sequence. | Y | Y | Y | Y |
| Lossless encoding | Y | Y | Y | Y |
| Main10 profile: Support for encoding 10-bit content. | Y | Y | Y | Y |
| 4:2:2 encoding | N | N | Y | N |
| 4:4:4 encoding | Y | Y | Y | Y |
| Motion estimation (ME) only mode: Capability to provide CTB level motion vectors and intra/inter modes. | Y | Y | Y | Y |
| 8K encoding: Support for encoding 8192 x 8192 Content. | Y | Y | Y | Y |
| Weighted prediction | Y | Y | Y | Y |
| Sample adaptive offset (SAO): Improves encoded video quality. | Y | Y | Y | Y |
| B frame: Improves encoded quality. | Y | Y | Y | Y |
| Multiple reference frames : Capability to use different reference frames | Y | Y | Y | Y |

## table 2

| Hardware Features | Ampere and TU GPUs | Ada GPUs | Blackwell GPUs | Jetson Thor |
| Main profile: Capability to encode YUV 420 8-bit and 10-bit content up to 8192 x 8192 content. | N | Y | Y | N |

## table 3

| Preset | RC Mode | Tuning Info | Turing | Ampere | Ada | Blackwell | Jetson Thor |
| P1 | CBR | LL | 855 | 868 | 910 | 977 | 724 |
| P1 | VBR | HQ | 833 | 846 | 885 | 948 | 713 |
| P3 | CBR | LL | 600 | 613 | 652 | 718 | 529 |
| P3 | VBR | HQ | 602 | 617 | 647 | 708 | 527 |
| P5 | CBR | LL | 271 | 273 | 291 | 323 | 236 |
| P5 | VBR | HQ | 264 | 266 | 283 | 317 | 230 |
| P7 | CBR | LL | 229 | 231 | 247 | 264 | 219 |
| P7 | VBR | HQ | 207 | 213 | 211 | 227 | 202 |

## table 4

| Preset | RC Mode | Tuning Info | Turing | Ampere | Ada | Blackwell | Jetson Thor |
| P1 | CBR | LL | 932 | 943 | 1055 | 1134 | 860 |
| P1 | VBR | HQ | 920 | 939 | 1037 | 1119 | 850 |
| P3 | CBR | LL | 463 | 467 | 494 | 529 | 402 |
| P3 | VBR | HQ | 552 | 557 | 706 | 947 | 579 |
| P5 | CBR | LL | 305 | 307 | 343 | 506 | 279 |
| P5 | VBR | HQ | 334 | 335 | 411 | 521 | 336 |
| P7 | CBR | LL | 306 | 308 | 343 | 464 | 279 |
| P7 | VBR | HQ | 171 | 171 | 181 | 181 | 148 |

## table 5

| Preset | RC Mode | Tuning Info | Ada | Blackwell |
| P1 | CBR | LL | 1090 | 1076 |
| P1 | VBR | HQ | 741 | 957 |
| P3 | CBR | LL | 774 | 798 |
| P3 | VBR | HQ | 549 | 678 |
| P5 | CBR | LL | 512 | 624 |
| P5 | VBR | HQ | 440 | 552 |
| P7 | CBR | LL | 356 | 395 |
| P7 | VBR | HQ | 323 | 401 |
