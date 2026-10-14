package util

import (
	"example.com/lib/data"
	"fmt"
)

func Yoink() int {
	fmt.Println("yoink")
	return data.Get()
}
