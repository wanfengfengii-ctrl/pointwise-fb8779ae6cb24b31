from collections import deque

from survey.ingest import Grid


def active_components(grid: Grid, threshold: int) -> dict[tuple[int, int], int]:
    if type(threshold) is not int or not 0 <= threshold <= 100:
        raise ValueError('threshold must be an integer from 0 to 100')
    active = dict.fromkeys((row, col)
                           for row, scores in enumerate(grid)
                           for col, score in enumerate(scores)
                           if score is not None and score >= threshold)
    labels = {}
    component = 0
    for seed in active:
        if seed in labels:
            continue
        labels[seed] = component
        frontier = deque([seed])
        while frontier:
            row, col = frontier.popleft()
            neighbors = ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1))
            for cell in neighbors:
                if cell in active and cell not in labels:
                    labels[cell] = component
                    frontier.append(cell)
        component += 1
    return labels
