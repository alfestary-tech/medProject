import matplotlib.pyplot as plt
import numpy as np
from parser.counter import prepare_mask_cv, prepare_mask_skimage

def compare_mask_methods(cts, info, roi_number, slice_idx=None):
    # Если срез не задан, берём средний срез, где есть контур этого ROI
    if slice_idx is None:
        suitable = [
            j for j, slice_info in enumerate(info)
            if any(
                roi_number in item and item[roi_number]["arrays"]
                for item in slice_info["countors"]
            )
        ]
        if not suitable:
            raise ValueError(f"Контуры ROI {roi_number} не найдены")
        slice_idx = suitable[len(suitable) // 2]

    slice_info = info[slice_idx]
    countor = next(
        item for item in slice_info["countors"] if roi_number in item
    )
    roi = countor[roi_number]

    shape = cts[slice_idx].shape
    old = prepare_mask_skimage(
        shape, countor, slice_info, roi_number).astype(bool)
    new = prepare_mask_cv(shape, countor, slice_info, roi_number).astype(bool)

    added = new & ~old    # есть только в OpenCV
    removed = old & ~new  # есть только в skimage

    def add_overlay(ax, mask, color, alpha=0.55):
        overlay = np.zeros((*mask.shape, 4), dtype=np.float32)
        overlay[..., :3] = color
        overlay[..., 3] = mask * alpha
        ax.imshow(overlay, interpolation="nearest")

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), constrained_layout=True)

    for ax in axes:
        ax.imshow(cts[slice_idx], cmap="gray", vmin=-200, vmax=300,
                  interpolation="nearest")
        ax.axis("off")

    add_overlay(axes[0], old, (0, 1, 0))  # зелёный
    axes[0].set_title("skimage")

    add_overlay(axes[1], new, (1, 0, 0))  # красный
    axes[1].set_title("OpenCV")

    add_overlay(axes[2], added, (1, 0, 0), alpha=0.85)
    add_overlay(axes[2], removed, (0, 0.5, 1), alpha=0.85)
    axes[2].set_title("Разница: красный — добавлено, синий — убрано")

    # Жёлтая линия — исходный контур из RTSTRUCT
    position = np.asarray(slice_info["patient_pos"], dtype=float)
    orientation = np.asarray(slice_info["orientation"], dtype=float)
    spacing = np.asarray(slice_info["pixel_spacing"], dtype=float)

    for data in roi["arrays"]:
        points = np.asarray(data, dtype=float).reshape(-1, 3)
        if len(points) < 3:
            continue

        delta = points - position
        cols = (delta @ orientation[:3]) / spacing[1]
        rows = (delta @ orientation[3:]) / spacing[0]

        for ax in axes:
            ax.plot(np.r_[cols, cols[0]], np.r_[rows, rows[0]],
                    color="yellow", linewidth=0.8)

    # Приближаем область ROI, чтобы были видны отдельные пиксели границы
    yy, xx = np.where(old | new)
    if len(xx):
        margin = 15
        for ax in axes:
            ax.set_xlim(max(0, xx.min() - margin),
                        min(shape[1] - 1, xx.max() + margin))
            ax.set_ylim(min(shape[0] - 1, yy.max() + margin),
                        max(0, yy.min() - margin))

    fig.suptitle(f"Срез {slice_idx}, ROI {roi_number}: {roi['name']}")
    plt.show()

    print(
        f"skimage: {old.sum()} пикселей; OpenCV: {new.sum()}; "
        f"добавлено: {added.sum()}; убрано: {removed.sum()}"
    )