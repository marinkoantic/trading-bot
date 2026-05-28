import random


def simulate_fill(quantity):

    fill_probability = random.uniform(0.90, 1.0)

    filled_quantity = quantity * fill_probability

    is_partial = filled_quantity < quantity

    return filled_quantity, is_partial