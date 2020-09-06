import torch
import torch.utils.data
from torchvision import transforms, datasets
from pathlib import Path
from torch.utils.data import Subset


def load_mnist_dataset(data_dir, batch_size, classes=None):
    transform_train = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=(0.1307,), std=(0.3081,))
    ])

    transform_test = transforms.Compose([
        transforms.ToTensor(),
        transforms.Normalize(mean=(0.1307,), std=(0.3081,))
    ])

    Path(data_dir).mkdir(exist_ok=True, parents=True)
    trainset = datasets.MNIST(root=data_dir, train=True, download=True, transform=transform_train)
    valset = datasets.MNIST(root=data_dir, train=False, download=True, transform=transform_test)

    if classes is not None:
        if len(classes) == 2:
            train_idx = torch.logical_or(trainset.targets == classes[0], trainset.targets == classes[1])
            val_idx = torch.logical_or(valset.targets == classes[0], valset.targets == classes[1])

            trainset.data, valset.data = trainset.data[train_idx], valset.data[val_idx]
            trainset.targets, valset.targets = trainset.targets[train_idx] == classes[1], valset.targets[val_idx] == classes[1]
        else:
            targets = trainset.targets
            target_indices = np.arange(len(targets))
            idx_to_keep = [i for i, x in enumerate(targets) if x in classes]
            train_idx = target_indices[idx_to_keep]
            trainset = Subset(trainset, train_idx)

            targets = valset.targets
            target_indices = np.arange(len(targets))
            idx_to_keep = [i for i, x in enumerate(targets) if x in classes]
            train_idx = target_indices[idx_to_keep]
            valset = Subset(valset, train_idx)

    if torch.cuda.is_available():
        trainloader = torch.utils.data.DataLoader(trainset, batch_size=batch_size, shuffle=True, pin_memory=True)
        valloader = torch.utils.data.DataLoader(valset, batch_size=batch_size, shuffle=False, pin_memory=True)

    else:
        trainloader = torch.utils.data.DataLoader(trainset, batch_size=batch_size, shuffle=True, pin_memory=False)
        valloader = torch.utils.data.DataLoader(valset, batch_size=batch_size, shuffle=False, pin_memory=False)

    return trainloader, valloader

