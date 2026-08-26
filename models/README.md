# Local model inventory

## `ppe_full.pt`

- Purpose: helmet and safety-vest detection.
- Labels: `Helmet`, `NO-Safety Vest`, `No Helmet`, `Safety Vest`, `shoes`.
- Source repository: <https://github.com/ApyCoder1/Real-Time-PPE-Detection-with-Django-and-Yolo>
- Upstream path: `app1/best.pt`.
- SHA-256: `8CD9DA16D7C806F8DF4CA1BB4AA8904EC8DD1606174127B1FACC3E55D82FD10C`.

The upstream repository does not provide sufficient model-card detail to treat
this checkpoint as certified for industrial use. It is suitable for a local
pilot only. Before production deployment, validate it against annotated images
from the actual electrical room and replace or fine-tune it if acceptance
targets are not met.

## `yolo11n.pt`

- Purpose: COCO `person` detection.
- Runtime: Ultralytics YOLO with ByteTrack.
- Documentation: <https://docs.ultralytics.com/models/yolo11/>

Review Ultralytics licensing before commercial deployment.
