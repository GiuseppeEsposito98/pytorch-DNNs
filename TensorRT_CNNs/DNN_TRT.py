import os
import h5py
import numpy as np
import tensorrt as trt
import pycuda.driver as cuda
import pycuda.autoinit
import argparse
import copy
import torch



def get_argparser():
    parser = argparse.ArgumentParser(description='DNN models')
    parser.add_argument('-t','--type', required=False, type=str, default="DNNs", help='golden')
    parser.add_argument('-n','--model_name', required=True, type=str, help='golden')
    parser.add_argument('-ln','--layer_number', required=False, type=int, help='golden')
    parser.add_argument('-bs','--batch_size', required=True, type=int, help='golden')
    parser.add_argument('-sz','--shape',required=False, nargs='+', type=int ,help="shape of the output layer")
    parser.add_argument('-onnx','--onnx', required=False, action='store_true', help='golden')
    parser.add_argument('-trt','--run_trt', required=False, action='store_true', help='golden')
    parser.add_argument('-fmt','--format', required=False, type=int, default=32, help='golden')
    return parser

DEBUG = 1

def main(args):

    path = os.path.dirname(__file__)
    # os.environ["CUDA_VISIBLE_DEVICES"]=""
    
    if args.format==16:
        target_dtype = np.float16
    else:
        target_dtype = np.float32
        
    current_path = os.path.dirname(__file__)
    path_dir = f"{args.type}/{args.model_name}"
    path_dir = os.path.join(current_path,path_dir)
    #self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    batch_size = args.batch_size
    if args.shape:
        TRT_output_shape = tuple(args.shape)

    layer_results = []

    TRT_model_name = f"{args.model_name}_pytorch.rtr"

    dataset_file = os.path.join(
            path_dir,
            f"Inputs_DNN.h5",
        )
    with h5py.File(dataset_file, "r") as hf:
        Input_dataset = np.array(hf["inputs"])
        labels = np.array(hf['labels'])


    with open(os.path.join(path_dir, TRT_model_name), "rb") as f:
        runtime = trt.Runtime(trt.Logger(trt.Logger.WARNING)) 
        engine = runtime.deserialize_cuda_engine(f.read())
        context = engine.create_execution_context()
        output = np.empty(TRT_output_shape, dtype = target_dtype) 
        if DEBUG: print(Input_dataset.shape)
        if DEBUG: print(TRT_output_shape)
        if DEBUG: print(output.shape)
        batch = 0
        sample_image = Input_dataset[
                    batch * batch_size : batch * batch_size + batch_size
                ].astype(target_dtype)
        d_input = cuda.mem_alloc(1 * sample_image.nbytes)
        d_output = cuda.mem_alloc(1 * output.nbytes)
        bindings = [int(d_input), int(d_output)]
        stream = cuda.Stream()
        # warming up
        # output=self.__TRT_forward_function(sample_image)
        # end warming up

    max_batches = float(float(len(Input_dataset)) / float(batch_size))
    #with torch.no_grad():
    for batch in range(0, int(np.ceil(max_batches))):
        img = Input_dataset[
            batch * batch_size : batch * batch_size + batch_size
        ].astype(target_dtype)

        cuda.memcpy_htod_async(d_input, img, stream)
        # execute model
        context.execute_async_v2(bindings, stream.handle, None)
        # transfer predictions back
        cuda.memcpy_dtoh_async(output, d_output, stream)
        # syncronize threads
        stream.synchronize()

        layer_results.append(copy.deepcopy(output.astype(np.float32)))
        if DEBUG: print(output)

    embeddings_outputs = np.concatenate(layer_results)

    if DEBUG: print(embeddings_outputs.shape)

    log_path_file = os.path.join(
        path_dir,
        f"Outputs_DNN.h5",
    )

    with h5py.File(log_path_file, "w") as hf:
        hf.create_dataset(
            "outputs", data=embeddings_outputs, compression="gzip"
        )

    with h5py.File(log_path_file, "r") as hf: 
        output_dataset = np.array(hf["outputs"])

    print(output_dataset.shape)

    gacc1=0
    gacc5=0
    # tot_imgs=0

    Golden_tensor = torch.from_numpy(output_dataset)
    Golden_labels = torch.from_numpy(labels)
    
    print(Golden_tensor.shape)
    print(Golden_labels.shape)
    
    
    pred, clas=Golden_tensor.topk(1,1,True,True)
    
    golden_class=clas.t()
    
    Res = golden_class.eq(Golden_labels[None].cpu())
    
    Gacc1 = Res[:1].flatten().sum(dtype=torch.float32)
    Gacc1 = Gacc1/len(Res[:1].flatten())
    print(Gacc1)
    # for outputs, label in zip(output_dataset, labels):
    #     pred, clas=outputs.cpu().topk(5,1,True,True)
    #     clas = clas.t()
    #     pred = pred.t()
    #     size = pred.shape
    #     # for idx,label in enumerate(labels):
    #     #     for pred_top in range(size[0]):
    #     #         print(f"{batch*BATCH_SIZE+idx}; {pred_top}; {label}; {clas[pred_top][idx]}; {pred[pred_top][idx]}")
    #     Res = clas.eq(label[None].cpu())

    #     acc1 = Res[:1].sum(dim=0,dtype=torch.float32)
    #     acc5 = Res[:5].sum(dim=0,dtype=torch.float32)            
    #     gacc1 += Res[:1].flatten().sum(dtype=torch.float32)
    #     gacc5 += Res[:5].flatten().sum(dtype=torch.float32)
    #     tot_imgs+=1

    
    

    # print(
    #         "Accuracy of the network on the {} test images: acc1 {} % acc5 {} % in sec".format(
    #             tot_imgs, 100 * gacc1 / tot_imgs,  100 * gacc5 / tot_imgs
    #         )
    #     )

if __name__ == "__main__":
    argparser = get_argparser()
    main(argparser.parse_args())