---
title: "Learn PyTorch – a quick code-based summary from PyTorch 60-min Blitz"
date: 2023-08-22
tags: ["data-science", "developer", "pytorch", "machine-learning"]
---

## Tensor

- Everything is represented as a tensor
- Computation occurs in compiled C++ code
- Over 300 mathematical operations available
- Default data type is float32
- Seeds enable reproducible data generation

### Standard NumPy-like Indexing

```python
import torch
tensor = torch.ones(4, 4)
tensor[:, 1] = 0
print(tensor)
```

### Joining Tensors

```python
# Concatenate along existing axis
torch.cat([tensor, tensor], dim=1)

# Stack creates new axis
torch.stack([tensor, tensor], dim=1)
```

### Multiplying Tensors

```python
# Element-wise product
print(tensor.mul(tensor))
print(tensor * tensor)

# Matrix multiplication
print(tensor.matmul(tensor))
print(tensor @ tensor)
```

### In-place Operations

Operations with underscore suffix modify tensors directly. These "save memory but discourage use when computing derivatives due to immediate history loss."

```python
tensor.add_(5)
```

### Bridge with NumPy

Changes in tensors reflect in corresponding NumPy arrays and vice versa.

```python
t = torch.ones(5)
n = t.numpy()
t.add_(5)  # Updates n automatically
```

## AutoGrad

Neural networks are "nested functions executed on input data."

### Training a Neural Network

**Forward Propagation**: Run input through each function layer

**Backward Propagation**: Compute gradients using chain rule

**Parameter Updates**: Adjust weights proportionally to error

### Single Training Step

```python
import torch
import torchvision

model = torchvision.models.resnet18(pretrained=True)
data = torch.rand(1, 3, 64, 64)
label = torch.rand(1, 1000)

prediction = model(data)  # forward pass
loss = (prediction - label).sum()
loss.backward()  # backward pass

optim = torch.optim.SGD(model.parameters(), lr=1e-2, momentum=0.9)
optim.step()
```

## Differentiation in Autograd

```python
a = torch.tensor([2.0, 3.0], requires_grad=True)
b = torch.tensor([6.0, 4.0], requires_grad=True)

Q = 3 * a ** 3 - b ** 2

external_grad = torch.tensor([1, 1])
Q.backward(gradient=external_grad)

a.grad  # Returns 9*a**2
```

For vector-valued functions, gradients form Jacobian matrices representing partial derivatives.
